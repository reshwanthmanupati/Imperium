#!/usr/bin/env python3
"""
IoT Node Simulator - Simulates IoT device behavior
Publishes sensor data via MQTT and responds to control messages
Exposes Prometheus metrics for monitoring
"""
import paho.mqtt.client as mqtt
import json
import time
import random
import logging
import os
from datetime import datetime
from prometheus_client import start_http_server, Counter, Gauge, Info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get node ID early for metric labels
NODE_ID = os.getenv('NODE_ID', 'node-1')

# ============== Prometheus Metrics ==============
# These metrics match what's documented in MONITORING_GUIDE.md

# Message counters
mqtt_messages_published_total = Counter(
    'mqtt_messages_published_total', 
    'Total MQTT messages published',
    ['node_id']
)
mqtt_messages_received_total = Counter(
    'mqtt_messages_received_total',
    'Total MQTT control messages received', 
    ['node_id']
)

# Configuration gauges (set via intents)
mqtt_qos_level = Gauge(
    'mqtt_qos_level',
    'Current MQTT QoS level (0, 1, or 2)',
    ['node_id']
)
mqtt_publish_interval_seconds = Gauge(
    'mqtt_publish_interval_seconds',
    'Seconds between data publishes (sampling rate)',
    ['node_id']
)
node_priority = Gauge(
    'node_priority',
    'Node priority level (1=low, 2=normal, 3=high)',
    ['node_id', 'priority']
)
node_enabled = Gauge(
    'node_enabled',
    'Whether node is enabled (1) or disabled (0)',
    ['node_id']
)

# Traffic metrics
node_bytes_sent_total = Counter(
    'node_bytes_sent_total',
    'Total bytes sent via MQTT',
    ['node_id']
)
node_latency_milliseconds = Gauge(
    'node_latency_milliseconds',
    'Simulated network latency in milliseconds',
    ['node_id']
)

# Sensor data gauges
iot_temperature_celsius = Gauge(
    'iot_temperature_celsius',
    'Current temperature reading',
    ['node_id']
)
iot_humidity_percent = Gauge(
    'iot_humidity_percent',
    'Current humidity reading',
    ['node_id']
)
iot_pressure_hpa = Gauge(
    'iot_pressure_hpa',
    'Current pressure reading',
    ['node_id']
)
iot_battery_percent = Gauge(
    'iot_battery_percent',
    'Current battery level',
    ['node_id']
)

# Node info
node_info = Info('iot_node', 'IoT node information')


class IoTNode:
    """Simulates an IoT device with Prometheus metrics"""
    
    def __init__(self, node_id, broker_host='mosquitto', broker_port=1883):
        self.node_id = node_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        
        # Node configuration (modifiable via MQTT control messages)
        self.config = {
            'sampling_rate': 5,  # seconds
            'qos': 0,
            'priority': 'normal',
            'bandwidth_limit': None,
            'enabled': True,
            'latency': 10  # simulated latency in ms
        }
        
        # Initialize Prometheus metrics with current config
        self._update_prometheus_metrics()
        
        # Set node info
        node_info.info({
            'node_id': node_id,
            'broker': broker_host,
            'version': '1.0.0'
        })
        
        # MQTT client
        self.client = mqtt.Client(client_id=node_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Topics
        self.data_topic = f"iot/{node_id}/data"
        self.control_topic = f"iot/{node_id}/control"
        self.status_topic = f"iot/{node_id}/status"
        
        self.running = False
    
    def _update_prometheus_metrics(self):
        """Update all Prometheus metrics with current configuration"""
        # QoS level
        mqtt_qos_level.labels(node_id=self.node_id).set(self.config['qos'])
        
        # Sampling rate
        mqtt_publish_interval_seconds.labels(node_id=self.node_id).set(self.config['sampling_rate'])
        
        # Priority (convert to numeric: low=1, normal=2, high=3)
        priority_map = {'low': 1, 'normal': 2, 'high': 3}
        priority_val = priority_map.get(self.config['priority'], 2)
        node_priority.labels(node_id=self.node_id, priority=self.config['priority']).set(priority_val)
        
        # Enabled status
        node_enabled.labels(node_id=self.node_id).set(1 if self.config['enabled'] else 0)
        
        # Latency
        node_latency_milliseconds.labels(node_id=self.node_id).set(self.config['latency'])
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            logger.info(f"Node {self.node_id} connected to MQTT broker")
            # Subscribe to control messages
            client.subscribe(self.control_topic, qos=1)
            # Publish status
            self.publish_status()
        else:
            logger.error(f"Connection failed with code {rc}")
    
    def on_message(self, client, userdata, msg):
        """Handle incoming control messages"""
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"Received control message: {payload}")
            mqtt_messages_received_total.labels(node_id=self.node_id).inc()
            
            # Update configuration
            if 'sampling_rate' in payload:
                self.config['sampling_rate'] = int(payload['sampling_rate'])
                logger.info(f"Updated sampling rate to {payload['sampling_rate']}s")
            
            if 'qos' in payload:
                self.config['qos'] = int(payload['qos'])
                logger.info(f"Updated QoS to {payload['qos']}")
            
            if 'priority' in payload:
                self.config['priority'] = payload['priority']
                logger.info(f"Updated priority to {payload['priority']}")
            
            if 'enabled' in payload:
                self.config['enabled'] = payload['enabled']
                logger.info(f"Node enabled: {payload['enabled']}")
            
            if 'latency' in payload:
                self.config['latency'] = int(payload['latency'])
                logger.info(f"Updated latency to {payload['latency']}ms")
            
            # Update Prometheus metrics with new config
            self._update_prometheus_metrics()
            
            # Acknowledge configuration change
            self.publish_status()
            
        except Exception as e:
            logger.error(f"Error processing control message: {e}")
    
    def publish_status(self):
        """Publish current node status"""
        status = {
            'node_id': self.node_id,
            'timestamp': datetime.now().isoformat(),
            'config': self.config,
            'status': 'online' if self.running else 'offline'
        }
        
        self.client.publish(
            self.status_topic,
            json.dumps(status),
            qos=1,
            retain=True
        )
    
    def generate_sensor_data(self):
        """Generate simulated sensor data"""
        return {
            'node_id': self.node_id,
            'timestamp': datetime.now().isoformat(),
            'temperature': round(20 + random.uniform(-5, 5), 2),
            'humidity': round(50 + random.uniform(-10, 10), 2),
            'pressure': round(1013 + random.uniform(-20, 20), 2),
            'battery': round(random.uniform(80, 100), 1)
        }
    
    def publish_data(self):
        """Publish sensor data and update Prometheus metrics"""
        if not self.config['enabled']:
            return
        
        data = self.generate_sensor_data()
        payload = json.dumps(data)
        payload_bytes = len(payload.encode())
        
        # Simulate latency
        time.sleep(self.config['latency'] / 1000.0)
        
        result = self.client.publish(
            self.data_topic,
            payload,
            qos=self.config['qos']
        )
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            # Update Prometheus metrics
            mqtt_messages_published_total.labels(node_id=self.node_id).inc()
            node_bytes_sent_total.labels(node_id=self.node_id).inc(payload_bytes)
            
            # Update sensor gauges
            iot_temperature_celsius.labels(node_id=self.node_id).set(data['temperature'])
            iot_humidity_percent.labels(node_id=self.node_id).set(data['humidity'])
            iot_pressure_hpa.labels(node_id=self.node_id).set(data['pressure'])
            iot_battery_percent.labels(node_id=self.node_id).set(data['battery'])
            
            logger.info(f"Published: {data['temperature']}°C, QoS={self.config['qos']}")
        else:
            logger.error(f"Failed to publish data: {result.rc}")
    
    def run(self):
        """Main run loop"""
        logger.info(f"Starting IoT Node: {self.node_id}")
        logger.info(f"Connecting to {self.broker_host}:{self.broker_port}")
        
        # Start Prometheus metrics server
        metrics_port = 8000 + int(self.node_id.split('-')[-1])
        start_http_server(metrics_port)
        logger.info(f"Metrics available at http://localhost:{metrics_port}")
        
        # Connect to MQTT broker
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            self.running = True
            
            # Main data publishing loop
            while self.running:
                self.publish_data()
                time.sleep(self.config['sampling_rate'])
                
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            logger.error(f"Error: {e}")
            self.running = False


if __name__ == '__main__':
    # Get configuration from environment
    node_id = os.getenv('NODE_ID', 'node-1')
    broker = os.getenv('MQTT_BROKER', 'localhost')
    port = int(os.getenv('MQTT_PORT', '1883'))
    
    # Create and run node
    node = IoTNode(node_id, broker, port)
    node.run()
