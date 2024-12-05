import sys
import json
import requests
from typing import Dict, Any
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from opentelemetry import trace

# Constants
API_BASE_URL = "http://localhost:5001"
DEFAULT_MODEL_URL = "https://raw.githubusercontent.com/alecjacobson/common-3d-test-models/refs/heads/master/data/alligator.obj"

tracer = trace.get_tracer(__name__)

class Vector3Input(QGroupBox):
    """A group of three input fields for x, y, z values"""
    def __init__(self, label: str, default_values: list = [0, 0, 0], tooltip: str = ""):
        super().__init__(label)
        layout = QGridLayout()
        layout.setSpacing(5)
        
        # Add coordinate labels
        layout.addWidget(QLabel("X:"), 0, 0)
        layout.addWidget(QLabel("Y:"), 0, 1)
        layout.addWidget(QLabel("Z:"), 0, 2)
        
        # Create input fields
        self.x_input = QLineEdit(str(default_values[0]))
        self.y_input = QLineEdit(str(default_values[1]))
        self.z_input = QLineEdit(str(default_values[2]))
        
        # Add input fields to layout
        for i, input_field in enumerate([self.x_input, self.y_input, self.z_input]):
            input_field.setFixedWidth(60)
            layout.addWidget(input_field, 1, i)
            
        if tooltip:
            self.setToolTip(tooltip)
            
        self.setLayout(layout)
        self.setMaximumHeight(80)  # Make the group box more compact
    
    def get_values(self) -> list:
        """Returns the vector3 values as a list of floats"""
        return [
            float(self.x_input.text()),
            float(self.y_input.text()),
            float(self.z_input.text())
        ]

class APITester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Viewer API Tester")
        self.setMinimumWidth(600)
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)
        
        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Add tabs
        tabs.addTab(self.create_add_entity_tab(), "Add Entity")
        tabs.addTab(self.create_update_entity_tab(), "Update Entity")
        tabs.addTab(self.create_remove_entity_tab(), "Remove Entity")
        tabs.addTab(self.create_window_control_tab(), "Window Control")
        
        # Add response section
        layout.addWidget(self.create_response_section())
        
    def create_add_entity_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        # Model Path input with label
        path_group = QGroupBox("Model Path")
        path_layout = QVBoxLayout(path_group)
        self.model_path_input = QLineEdit(DEFAULT_MODEL_URL)
        self.model_path_input.setToolTip("Enter the URL or local path to your 3D model")
        path_layout.addWidget(self.model_path_input)
        layout.addWidget(path_group)
        
        # Create grid for vector inputs
        vectors_layout = QGridLayout()
        vectors_layout.setSpacing(10)
        
        # Vector3 inputs with tooltips
        self.position_input = Vector3Input("Position", [0, 0, 0], 
                                         "Set the position in 3D space (X, Y, Z)")
        self.rotation_input = Vector3Input("Rotation", [0, 0, 0],
                                         "Set the rotation in degrees (Pitch, Yaw, Roll)")
        self.scale_input = Vector3Input("Scale", [0.01, 0.01, 0.01],
                                      "Set the scale factors (X, Y, Z)")
        self.color_input = Vector3Input("Object Color", [1, 1, 1],
                                      "Set the RGB color values (0-1)")
        
        # Add vector inputs in a 2x2 grid
        vectors_layout.addWidget(self.position_input, 0, 0)
        vectors_layout.addWidget(self.rotation_input, 0, 1)
        vectors_layout.addWidget(self.scale_input, 1, 0)
        vectors_layout.addWidget(self.color_input, 1, 1)
        layout.addLayout(vectors_layout)
        
        # Add button
        add_button = QPushButton("Add Entity")
        add_button.clicked.connect(self.add_entity)
        add_button.setStyleSheet("QPushButton { padding: 5px; }")
        layout.addWidget(add_button)
        
        layout.addStretch()
        return widget
    
    def create_update_entity_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        # Entity ID input
        id_group = QGroupBox("Entity ID")
        id_layout = QHBoxLayout(id_group)
        self.update_entity_id = QLineEdit("1")
        self.update_entity_id.setFixedWidth(60)
        self.update_entity_id.setToolTip("Enter the ID of the entity to update")
        id_layout.addWidget(self.update_entity_id)
        id_layout.addStretch()
        layout.addWidget(id_group)
        
        # Vector3 inputs in a grid
        vectors_layout = QGridLayout()
        vectors_layout.setSpacing(10)
        
        self.update_position = Vector3Input("Position")
        self.update_rotation = Vector3Input("Rotation")
        self.update_scale = Vector3Input("Scale", [0.01, 0.01, 0.01])
        self.update_color = Vector3Input("Object Color", [1, 1, 1])
        
        vectors_layout.addWidget(self.update_position, 0, 0)
        vectors_layout.addWidget(self.update_rotation, 0, 1)
        vectors_layout.addWidget(self.update_scale, 1, 0)
        vectors_layout.addWidget(self.update_color, 1, 1)
        layout.addLayout(vectors_layout)
        
        # Update button
        update_button = QPushButton("Update Entity")
        update_button.clicked.connect(self.update_entity)
        update_button.setStyleSheet("QPushButton { padding: 5px; }")
        layout.addWidget(update_button)
        
        layout.addStretch()
        return widget
    
    def create_remove_entity_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        # Entity ID input
        id_group = QGroupBox("Entity ID")
        id_layout = QHBoxLayout(id_group)
        self.remove_entity_id = QLineEdit("1")
        self.remove_entity_id.setFixedWidth(60)
        self.remove_entity_id.setToolTip("Enter the ID of the entity to remove")
        id_layout.addWidget(self.remove_entity_id)
        id_layout.addStretch()
        layout.addWidget(id_group)
        
        # Remove button
        remove_button = QPushButton("Remove Entity")
        remove_button.clicked.connect(self.remove_entity)
        remove_button.setStyleSheet("QPushButton { padding: 5px; }")
        layout.addWidget(remove_button)
        
        layout.addStretch()
        return widget
    
    def create_window_control_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        # Control buttons
        buttons_group = QGroupBox("Window Controls")
        buttons_layout = QVBoxLayout(buttons_group)
        
        open_button = QPushButton("Open Window")
        open_button.clicked.connect(self.open_window)
        open_button.setToolTip("Open the 3D viewer window")
        
        health_button = QPushButton("Health Check")
        health_button.clicked.connect(self.health_check)
        health_button.setToolTip("Check if the server is running")
        
        for button in [open_button, health_button]:
            button.setStyleSheet("QPushButton { padding: 5px; }")
            buttons_layout.addWidget(button)
            
        layout.addWidget(buttons_group)
        layout.addStretch()
        return widget
    
    def create_response_section(self) -> QWidget:
        group = QGroupBox("Response")
        layout = QVBoxLayout(group)
        layout.setSpacing(5)
        
        # Status with icon
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))
        self.status_label = QLabel()
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Response data
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setMaximumHeight(100)
        layout.addWidget(self.response_text)
        
        return group
    
    def send_request(self, endpoint: str, method: str = "POST", 
                    data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Sends a request to the API and returns the response"""
        url = f"{API_BASE_URL}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            else:
                response = requests.post(url, headers=headers, json=data)
            
            result = {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": response.json()
            }
        except Exception as e:
            result = {
                "success": False,
                "status_code": 500,
                "data": {"error": str(e)}
            }
            
        self.update_response(result)
        return result
    
    def update_response(self, response: Dict[str, Any]):
        """Updates the response section"""
        status_text = f"Success ({response['status_code']})" if response['success'] else f"Failed ({response['status_code']})"
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(
            "color: green;" if response['success'] else "color: red;"
        )
        
        # Extract just the message or error from the response data
        response_data = response["data"]
        if response['success']:
            message = response_data.get("message", "Success (no message provided)")
        else:
            message = response_data.get("error", "Unknown error occurred")
            
        self.response_text.setText(message)
    
    def add_entity(self):
        """Handles Add Entity button click"""
        data = {
            "modelPath": self.model_path_input.text(),
            "position": self.position_input.get_values(),
            "rotation": self.rotation_input.get_values(),
            "scale": self.scale_input.get_values(),
            "objectColor": self.color_input.get_values(),
        }
        self.send_request("add_entity", "POST", data)
    
    def update_entity(self):
        """Handles Update Entity button click"""
        entity_id = int(self.update_entity_id.text())
        data = {
            "position": self.update_position.get_values(),
            "rotation": self.update_rotation.get_values(),
            "scale": self.update_scale.get_values(),
            "objectColor": self.update_color.get_values(),
        }
        
        with tracer.start_as_current_span("update_entity"):
            self.send_request(f"update_entity/{entity_id}", "POST", data)
    
    def remove_entity(self):
        """Handles Remove Entity button click"""
        entity_id = int(self.remove_entity_id.text())
        
        with tracer.start_as_current_span("remove_entity"):
            self.send_request(f"remove_entity/{entity_id}", "POST")
    
    def open_window(self):
        """Handles Open Window button click"""
        self.send_request("open_window", "POST")
    
    def health_check(self):
        """Handles Health Check button click"""
        self.send_request("health_check", "GET")

def main():
    app = QApplication(sys.argv)
    
    # Set application-wide stylesheet
    app.setStyleSheet("""
        QGroupBox {
            font-weight: bold;
            border: 1px solid #cccccc;
            border-radius: 3px;
            margin-top: 0.5em;
            padding-top: 0.5em;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 7px;
            padding: 0 3px 0 3px;
        }
        QPushButton {
            background-color: #f0f0f0;
            border: 1px solid #cccccc;
            border-radius: 3px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        QLineEdit {
            padding: 2px;
            border: 1px solid #cccccc;
            border-radius: 2px;
        }
    """)
    
    window = APITester()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
