from flask import Flask, render_template, request, jsonify

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.config_manager import ConfigManager
app = Flask(__name__)
config = ConfigManager()
@app.route('/')
def index():
    """Main control panel page"""
    return render_template('index.html')
@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current battle config"""
    battle_config = config.get_battle_config()
    return jsonify({
        'turn': battle_config.turn,
        'refresh': battle_config.refresh,
        'until_finish': battle_config.until_finish,
        'trigger_skip': battle_config.trigger_skip,
        'think_time_min': battle_config.think_time_min,
        'think_time_max': battle_config.think_time_max,
        'current_state': config.current_state.value
    })
@app.route('/api/config', methods=['POST'])
def update_config():
    """Update battle config"""
    data = request.json
    config.update_battle_config(**data)
    return jsonify({'status': 'ok', 'updated': data})
@app.route('/api/state', methods=['GET'])
def get_state():
    """Get current state"""
    return jsonify({'state': config.current_state.value})
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)