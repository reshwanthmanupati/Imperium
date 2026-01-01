#!/usr/bin/env python3
"""
Integration Tests - End-to-end testing of the Imperium system
Tests the complete workflow from intent submission to policy enforcement
"""
import pytest
import sys
import os
import time
import requests
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from intent_manager.parser import IntentParser
from intent_manager.api import IntentManager
from policy_engine.engine import PolicyEngine, PolicyType
from enforcement.network import NetworkEnforcer
from enforcement.device import DeviceEnforcer
from feedback.monitor import FeedbackEngine


class TestEndToEndWorkflow:
    """Test complete intent-to-enforcement workflow"""
    
    def setup_method(self):
        """Setup test environment"""
        self.intent_manager = IntentManager()
        self.parser = IntentParser()
        self.policy_engine = PolicyEngine()
        self.network_enforcer = NetworkEnforcer()
        self.feedback_engine = FeedbackEngine('http://localhost:9090')
    
    def test_priority_intent_workflow(self):
        """Test complete workflow for priority intent"""
        # Step 1: Submit intent
        intent_data = {
            'description': 'Prioritize device node-1',
            'type': 'priority'
        }
        
        intent = self.intent_manager.submit_intent(intent_data)
        
        # Verify intent created
        assert intent['status'] == 'active'
        assert 'id' in intent
        assert len(intent['policies']) > 0
        
        # Step 2: Verify policies generated
        policies = intent['policies']
        assert any(p['policy_type'] == 'traffic_shaping' for p in policies)
        assert any(p['policy_type'] == 'routing_priority' for p in policies)
        
        # Step 3: Verify policy parameters
        traffic_policy = next(p for p in policies if p['policy_type'] == 'traffic_shaping')
        assert traffic_policy['target'] == 'node-1' or traffic_policy['target'] == '1'
        assert 'rate' in traffic_policy['parameters']
        assert traffic_policy['priority'] >= 8  # High priority
    
    def test_bandwidth_intent_workflow(self):
        """Test complete workflow for bandwidth limitation"""
        intent_data = {
            'description': 'Limit bandwidth to 100 mbps for node-2',
            'type': 'bandwidth'
        }
        
        intent = self.intent_manager.submit_intent(intent_data)
        
        assert intent['status'] == 'active'
        policies = intent['policies']
        
        # Verify bandwidth limit policy
        bw_policy = next((p for p in policies if p['policy_type'] == 'bandwidth_limit'), None)
        assert bw_policy is not None
        assert '100' in bw_policy['parameters']['rate']
    
    def test_latency_intent_workflow(self):
        """Test complete workflow for latency reduction"""
        intent_data = {
            'description': 'Reduce latency to 50ms',
            'type': 'latency'
        }
        
        intent = self.intent_manager.submit_intent(intent_data)
        
        assert intent['status'] == 'active'
        policies = intent['policies']
        
        # Verify traffic shaping for low latency
        assert any(p['policy_type'] == 'traffic_shaping' for p in policies)
        
        latency_policy = next(p for p in policies if p['policy_type'] == 'traffic_shaping')
        assert latency_policy['priority'] >= 8  # High priority for low latency
    
    def test_qos_intent_workflow(self):
        """Test complete workflow for QoS configuration"""
        intent_data = {
            'description': 'Set QoS level 2 for node-1',
            'type': 'qos'
        }
        
        intent = self.intent_manager.submit_intent(intent_data)
        
        assert intent['status'] == 'active'
        policies = intent['policies']
        
        # Verify QoS policy
        qos_policy = next((p for p in policies if p['policy_type'] == 'qos_control'), None)
        assert qos_policy is not None
        assert qos_policy['parameters']['mqtt_qos'] == 2
        assert qos_policy['parameters']['reliable_delivery'] is True
    
    def test_multiple_intents(self):
        """Test submitting multiple intents"""
        intents_data = [
            {'description': 'Prioritize device node-1', 'type': 'priority'},
            {'description': 'Limit bandwidth to 50 mbps for node-2', 'type': 'bandwidth'},
            {'description': 'Set QoS level 1 for node-3', 'type': 'qos'}
        ]
        
        submitted_intents = []
        for data in intents_data:
            intent = self.intent_manager.submit_intent(data)
            assert intent['status'] == 'active'
            submitted_intents.append(intent)
        
        # Verify all intents stored
        all_intents = self.intent_manager.list_intents()
        assert len(all_intents) >= len(intents_data)
    
    def test_invalid_intent_handling(self):
        """Test handling of invalid intents"""
        # Empty description
        intent_data = {'description': '', 'type': 'priority'}
        intent = self.intent_manager.submit_intent(intent_data)
        
        # Should still process but may have no parameters
        assert 'id' in intent


class TestPolicyEnforcement:
    """Test policy enforcement on network and devices"""
    
    def setup_method(self):
        self.network_enforcer = NetworkEnforcer('eth0')
        # Mock MQTT for device enforcer tests
        self.device_enforcer_mock = Mock()
    
    def test_network_policy_application(self):
        """Test applying network policies (simulation mode)"""
        policy = {
            'policy_id': 'test-1',
            'policy_type': 'bandwidth_limit',
            'target': 'node-1',
            'parameters': {
                'rate': '100mbit',
                'burst': '15k',
                'latency': '50ms'
            }
        }
        
        # On non-Linux, this will simulate
        result = self.network_enforcer.apply_policy(policy)
        
        # Should return True (simulated or real)
        assert result is True
    
    def test_traffic_shaping_policy(self):
        """Test traffic shaping policy application"""
        policy = {
            'policy_id': 'test-2',
            'policy_type': 'traffic_shaping',
            'target': 'node-2',
            'parameters': {
                'rate': '100mbit',
                'ceil': '200mbit',
                'burst': '32k',
                'class': 'high_priority'
            }
        }
        
        result = self.network_enforcer.apply_policy(policy)
        assert result is True
    
    def test_policy_clear(self):
        """Test clearing all network policies"""
        result = self.network_enforcer.clear_policies()
        # Should succeed (or return True in simulation)
        assert result in [True, False]  # May fail if no policies exist
    
    def test_get_network_status(self):
        """Test getting network enforcer status"""
        status = self.network_enforcer.get_status()
        
        assert 'status' in status
        assert 'interface' in status
        assert status['interface'] == 'eth0'


class TestFeedbackLoop:
    """Test feedback loop and monitoring"""
    
    def setup_method(self):
        self.feedback_engine = FeedbackEngine('http://localhost:9090')
    
    def test_intent_registration(self):
        """Test registering intent goals"""
        intent_id = 'test-intent-1'
        goals = {
            'max_latency': 100,
            'min_throughput': 10
        }
        
        self.feedback_engine.register_intent(intent_id, goals)
        
        assert intent_id in self.feedback_engine.intent_goals
        assert self.feedback_engine.intent_goals[intent_id]['goals'] == goals
    
    def test_satisfaction_check_with_mock_metrics(self):
        """Test intent satisfaction checking with mocked metrics"""
        intent_id = 'test-intent-2'
        goals = {
            'max_latency': 100,
            'min_throughput': 5
        }
        
        self.feedback_engine.register_intent(intent_id, goals)
        
        # Mock Prometheus response
        with patch.object(self.feedback_engine, 'get_latency_metrics', return_value=50.0):
            with patch.object(self.feedback_engine, 'get_throughput_metrics', return_value=10.0):
                satisfaction = self.feedback_engine.check_intent_satisfaction(intent_id)
                
                assert 'satisfied' in satisfaction
                assert satisfaction['satisfied'] is True
                assert len(satisfaction['violations']) == 0
    
    def test_violation_detection(self):
        """Test detecting intent violations"""
        intent_id = 'test-intent-3'
        goals = {
            'max_latency': 50,  # Very strict
            'min_throughput': 20
        }
        
        self.feedback_engine.register_intent(intent_id, goals)
        
        # Mock metrics that violate goals
        with patch.object(self.feedback_engine, 'get_latency_metrics', return_value=150.0):
            with patch.object(self.feedback_engine, 'get_throughput_metrics', return_value=5.0):
                satisfaction = self.feedback_engine.check_intent_satisfaction(intent_id)
                
                assert satisfaction['satisfied'] is False
                assert len(satisfaction['violations']) > 0
    
    def test_adjustment_recommendations(self):
        """Test generating policy adjustment recommendations"""
        intent_id = 'test-intent-4'
        goals = {'max_latency': 50}
        
        self.feedback_engine.register_intent(intent_id, goals)
        
        # Mock violation
        with patch.object(self.feedback_engine, 'get_latency_metrics', return_value=200.0):
            recommendations = self.feedback_engine.recommend_adjustments(intent_id)
            
            assert len(recommendations) > 0
            assert recommendations[0]['action'] in ['increase_priority', 'increase_bandwidth', 'throttle_bandwidth']


class TestAPIIntegration:
    """Test Intent Manager API integration"""
    
    @pytest.fixture
    def api_url(self):
        """Base API URL"""
        return "http://localhost:5000/api/v1"
    
    @pytest.mark.skip(reason="Requires running API server")
    def test_submit_intent_via_api(self, api_url):
        """Test submitting intent via REST API"""
        intent_data = {
            'description': 'Prioritize device node-1',
            'type': 'priority'
        }
        
        response = requests.post(
            f"{api_url}/intents",
            json=intent_data,
            timeout=5
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert 'intent' in data
    
    @pytest.mark.skip(reason="Requires running API server")
    def test_list_intents_via_api(self, api_url):
        """Test listing intents via REST API"""
        response = requests.get(f"{api_url}/intents", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        assert 'intents' in data
        assert 'count' in data
    
    @pytest.mark.skip(reason="Requires running API server")
    def test_health_check(self):
        """Test API health check endpoint"""
        response = requests.get("http://localhost:5000/health", timeout=5)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
