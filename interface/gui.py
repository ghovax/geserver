import gi
import requests
from gi.repository import Gtk, Pango, GLib, Gdk
import logging
import socketio
import time

gi.require_version("Gtk", "3.0")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Define a constant for the base URL
BASE_URL = "http://localhost:5001"

# Initialize SocketIO client
sio = socketio.Client()


class APIGUI(Gtk.Window):
    def __init__(self):
        super().__init__(title="API Tester")
        self.set_border_width(10)
        self.set_default_size(200, 200)
        self.set_resizable(False)

        self.action_combo = Gtk.ComboBoxText()
        self.action_combo.append_text("Create entity")
        self.action_combo.append_text("Remove entity")
        self.action_combo.append_text("Get entity")
        self.action_combo.append_text("Add component to entity")
        self.action_combo.append_text("Others")
        self.action_combo.set_active(0)
        self.action_combo.connect("changed", self.on_action_changed)

        self.input_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.entry_fields = {}

        self.response_view = Gtk.TextView()
        self.response_view.set_editable(False)
        self.response_view.set_wrap_mode(Gtk.WrapMode.WORD)

        font_description = Pango.FontDescription("Menlo 11")
        self.response_view.override_font(font_description)

        self.response_scroll = Gtk.ScrolledWindow()
        self.response_scroll.set_vexpand(True)
        self.response_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self.response_scroll.add(self.response_view)

        self.on_action_changed(self.action_combo)

        # Create a label for the server status
        status_label = Gtk.Label(label="Server status")

        # Create radio buttons for server status
        self.status_online = Gtk.RadioButton.new_with_label(None, "Online")
        self.status_offline = Gtk.RadioButton.new_with_label_from_widget(
            self.status_online, "Offline"
        )
        self.status_offline.set_active(True)  # Start with Offline

        # Disable the radio buttons to make them unselectable
        self.status_online.set_sensitive(False)
        self.status_offline.set_sensitive(False)

        # Create a Box to hold the radio buttons
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_box.pack_start(
            status_label, False, False, 0
        )  # Add the status label first
        status_box.pack_start(self.status_online, False, False, 0)
        status_box.pack_start(self.status_offline, False, False, 0)

        # Create a label for the API endpoints
        api_label = Gtk.Label(label="API endpoints")
        api_label.set_halign(Gtk.Align.START)  # Align the label to the left

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.pack_start(status_box, False, False, 0)  # Add status box to main box

        # Add a horizontal separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.pack_start(separator, False, False, 0)  # Add the separator

        # Add the API endpoints label
        main_box.pack_start(api_label, False, False, 0)  # Add the API endpoints label
        main_box.pack_start(self.action_combo, False, False, 0)
        main_box.pack_start(self.input_box, True, True, 0)

        # Add a horizontal separator above the console
        response_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.pack_start(response_separator, False, False, 0)  # Add the separator

        main_box.pack_start(self.response_scroll, True, True, 0)
        self.add(main_box)

        # Connect to the WebSocket server
        try:
            sio.connect(BASE_URL)
            self.status_online.set_active(
                True
            )  # Set to online if connection is successful
            self.status_offline.set_active(False)
        except Exception as exception:
            self.status_online.set_active(False)  # Set to offline if connection fails
            self.status_offline.set_active(True)

        # Listen for status updates
        sio.on("status_response", self.update_status_indicator)

        # Listen for disconnection event
        sio.on("disconnect", self.on_disconnect)

        # Listen for connection event
        sio.on("connect", self.on_connect)

        # Listen for connection error event
        sio.on("connect_error", self.on_connect_error)

        # Add a reconnect handler
        sio.on("reconnect", self.on_reconnect)

        # Add a reconnect attempt handler
        sio.on("reconnect_attempt", self.on_reconnect_attempt)

        # Request initial status only if connected
        if sio.connected:
            self.request_status()
        else:
            logger.warning("WebSocket is not connected at startup")

        # Add a variable to track the number of attempts
        self.reconnect_attempts = 0

        # Start a timer to check the connection status every 1 second
        GLib.timeout_add(1000, self.check_connection_status)

    def on_action_changed(self, combo):
        action = combo.get_active_text()
        self.clear_input_fields()

        if action == "Create entity":
            self.setup_create_entity_fields()
        elif action == "Remove entity":
            self.setup_remove_entity_fields()
        elif action == "Get entity":
            self.setup_get_entity_fields()
        elif action == "Add component to entity":
            self.setup_add_component_to_entity_fields()
        elif action == "Others":
            self.setup_others_fields()

        self.show_all()

    def setup_create_entity_fields(self):
        self.add_input_field("Name")
        self.add_input_field("Target scene")
        self.add_input_field("Tags (comma-separated)")
        self.add_submit_button("Submit create entity request", self.on_create_entity)

    def setup_remove_entity_fields(self):
        self.add_input_field("Entity ID")
        self.add_submit_button("Submit remove entity request", self.on_remove_entity)

    def setup_get_entity_fields(self):
        self.add_input_field("Entity ID")
        self.add_submit_button("Submit get entity request", self.on_get_entity)

    def setup_add_component_to_entity_fields(self):
        self.add_input_field("Entity ID")
        self.component_combo = Gtk.ComboBoxText()
        self.component_combo.append_text("Transform")
        self.component_combo.set_active(0)
        self.component_combo.connect("changed", self.on_component_changed)
        self.input_box.pack_start(self.component_combo, False, False, 0)
        self.add_submit_button(
            "Submit add component to entity request", self.on_add_component_to_entity
        )

        self.on_component_changed(self.component_combo)

    def on_component_changed(self, combo):
        self.clear_transform_fields()
        component_type = combo.get_active_text()

        if component_type == "Transform":
            self.add_transform_fields()

    def add_transform_fields(self):
        self.add_input_field("Position")
        self.add_input_field("Rotation")
        self.add_input_field("Scale")

    def clear_transform_fields(self):
        for label_text in ["Position", "Rotation", "Scale"]:
            if label_text in self.entry_fields:
                entry = self.entry_fields[label_text]
                self.input_box.remove(entry.get_parent())
                del self.entry_fields[label_text]

    def setup_others_fields(self):
        self.add_others_buttons()
        self.clear_submit_button()

    def add_input_field(self, label_text):
        label = Gtk.Label(label=label_text)
        label.set_halign(Gtk.Align.START)
        entry = Gtk.Entry()
        self.input_box.pack_start(label, False, False, 0)
        self.input_box.pack_start(entry, False, False, 0)
        self.entry_fields[label_text] = entry
        return entry

    def add_submit_button(self, button_label, callback):
        self.clear_submit_button()
        submit_button = Gtk.Button(label=button_label)
        submit_button.connect("clicked", callback)
        self.input_box.pack_start(submit_button, False, False, 0)

    def clear_submit_button(self):
        for widget in self.input_box.get_children():
            if isinstance(widget, Gtk.Button) and widget.get_label().startswith(
                "Submit"
            ):
                self.input_box.remove(widget)

    def add_others_buttons(self):
        shutdown_button = Gtk.Button(label="Shutdown")
        shutdown_button.connect("clicked", self.on_shutdown)
        self.input_box.pack_start(shutdown_button, False, False, 0)

    def clear_input_fields(self):
        for widget in self.input_box.get_children():
            if isinstance(widget, Gtk.Label) or isinstance(widget, Gtk.Entry):
                self.input_box.remove(widget)
            elif isinstance(widget, Gtk.Button) and widget.get_label() == "Shutdown":
                self.input_box.remove(widget)
            elif isinstance(widget, Gtk.ComboBoxText):
                self.input_box.remove(widget)
        self.entry_fields.clear()

    def on_create_entity(self, button):
        data = {
            "name": self.entry_fields["Name"].get_text(),
            "targetScene": self.entry_fields["Target scene"].get_text(),
            "tags": self.entry_fields["Tags (comma-separated)"].get_text().split(","),
        }
        response = requests.post(f"{BASE_URL}/create_entity", json=data)
        self.display_response(response.json())

    def on_remove_entity(self, button):
        entity_id = self.entry_fields["Entity ID"].get_text()
        response = requests.delete(f"{BASE_URL}/remove_entity/{entity_id}")
        self.display_response(response.json())

    def on_get_entity(self, button):
        entity_id = self.entry_fields["Entity ID"].get_text()
        response = requests.get(f"{BASE_URL}/get_entity/{entity_id}")
        self.display_response(response.json())

    def on_shutdown(self, button):
        response = requests.post(f"{BASE_URL}/shutdown")
        self.display_response(response.json())

    def on_add_component_to_entity(self, button):
        entity_id = self.entry_fields["Entity ID"].get_text()
        component_type = self.component_combo.get_active_text()

        # Gather data for the Transform component
        if component_type == "Transform":
            position = self.entry_fields["Position"].get_text().split(",")
            rotation = self.entry_fields["Rotation"].get_text().split(",")
            scale = self.entry_fields["Scale"].get_text().split(",")

            # Check if all inputs are valid before converting to float
            fields = {"Position": position, "Rotation": rotation, "Scale": scale}
            if not all(
                all(coordinate.replace(".", "", 1).isdigit() for coordinate in coords)
                for coords in fields.values()
            ):
                for label, coords in fields.items():
                    if not all(
                        coordinate.replace(".", "", 1).isdigit()
                        for coordinate in coords
                    ):
                        self.highlight_label(label)
                return

            # Convert string inputs to float
            try:
                position = [float(coordinate) for coordinate in position]
                rotation = [float(coordinate) for coordinate in rotation]
                scale = [float(coordinate) for coordinate in scale]
                # Clear highlights if inputs are valid
                self.clear_highlight()
            except ValueError:
                # This block should not be reached due to the previous checks
                return

            data = {
                "type": "transform",
                "data": {"position": position, "rotation": rotation, "scale": scale},
            }
        else:
            logger.error("Invalid component type")
            return

        # Send the request to the server
        response = requests.post(
            f"{BASE_URL}/add_component_to_entity/{entity_id}", json=data
        )

        # Check for errors in the response
        if response.status_code != 200:
            self.display_response(
                response.json()
            )  # Display the error message from the server
            return

        self.display_response(response.json())

    def display_response(self, response_data):
        GLib.idle_add(self._update_response_view, response_data)

    def _update_response_view(self, response_data):
        self.response_view.get_buffer().set_text("")
        response_str = str(response_data)
        self.response_view.get_buffer().insert_at_cursor(response_str)
        return False

    def highlight_label(self, label_text):
        if label_text in self.entry_fields:
            label = self.input_box.get_children()[
                self.input_box.get_children().index(self.entry_fields[label_text]) - 1
            ]
            label.override_color(
                Gtk.StateFlags.NORMAL, Gdk.RGBA(1, 0, 0, 1)
            )  # Red color for label

    def clear_highlight(self):
        for label_text in ["Position", "Rotation", "Scale"]:
            if label_text in self.entry_fields:
                label = self.input_box.get_children()[
                    self.input_box.get_children().index(self.entry_fields[label_text])
                    - 1
                ]
                label.override_color(
                    Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 0, 0, 1)
                )  # Reset to default color

    def update_status_indicator(self, data):
        """Update the radio button based on server status."""
        if data["status"] == "success":
            self.status_online.set_active(True)
            self.status_offline.set_active(False)
        else:
            self.status_online.set_active(False)
            self.status_offline.set_active(True)

    def request_status(self):
        """Request the server status via WebSocket."""
        if sio.connected:  # Check if connected before emitting
            sio.emit("request_status")

    def on_connect(self):
        """Handle WebSocket reconnection."""
        self.status_online.set_active(True)  # Set to online when connected
        self.status_offline.set_active(False)
        self.request_status()  # Request the server status when reconnected

    def on_disconnect(self):
        """Handle WebSocket disconnection."""
        self.status_online.set_active(False)
        self.status_offline.set_active(True)
        GLib.timeout_add(
            1000, self.try_reconnect
        )  # Attempt to reconnect after 1 second

    def try_reconnect(self):
        """Attempt to reconnect to the WebSocket."""
        if sio.connected:  # Check if already connected
            self.reconnect_attempts = 0  # Reset attempts
            self.on_connect()  # Call on_connect to update status
            return False  # Stop the timeout

        try:
            sio.connect(BASE_URL)  # Attempt to reconnect
            self.reconnect_attempts = 0  # Reset attempts on success
            # Ensure on_connect is called after successful connection
            sio.on("connect", self.on_connect)  # Listen for the connect event
            return False  # Stop the timeout after one attempt
        except Exception as e:
            self.reconnect_attempts += 1
            wait_time = min(
                60, 2**self.reconnect_attempts
            )  # Exponential backoff, max 60 seconds
            GLib.timeout_add(
                wait_time * 1000, self.try_reconnect
            )  # Retry after wait_time
            return True  # Keep trying until successful

    def on_connect_error(self, data):
        """Handle WebSocket connection error."""
        self.status_online.set_active(False)
        self.status_offline.set_active(True)

    def on_reconnect(self, *args):
        """Handle WebSocket reconnection."""
        self.request_status()  # Request the server status when reconnected

    def on_reconnect_attempt(self, *args):
        """Handle WebSocket reconnection attempts."""
        pass  # No logging for reconnect attempts

    def on_destroy(self, widget):
        """Handle window destruction."""
        sio.disconnect()  # Disconnect from the WebSocket
        Gtk.main_quit()  # Stop the GTK main loop

    def check_connection_status(self):
        """Check if the WebSocket server is online and update the GUI accordingly."""
        if not sio.connected:
            try:
                sio.connect(BASE_URL)  # Attempt to connect
                self.on_connect()  # Call on_connect to update status
            except Exception:
                pass  # Connection failed, do nothing

        return True  # Keep the timer running


if __name__ == "__main__":
    window = APIGUI()
    window.connect(
        "destroy", window.on_destroy
    )  # Connect the destroy event to the on_destroy method
    window.show_all()
    Gtk.main()
