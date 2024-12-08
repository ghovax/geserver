import gi
import requests
from gi.repository import Gtk, Pango, GLib, Gdk
import logging
import socketio
import time
from typing import Optional, Dict

gi.require_version("Gtk", "3.0")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Define a constant for the base URL
BASE_URL = "http://localhost:5001"

# Initialize SocketIO client
sio = socketio.Client()

# Global state variables to replace class instance variables
window: Optional[Gtk.Window] = None
action_combo: Optional[Gtk.ComboBoxText] = None
input_box: Optional[Gtk.Box] = None
entry_fields: Dict[str, Gtk.Entry] = {}
response_view: Optional[Gtk.TextView] = None
response_scroll: Optional[Gtk.ScrolledWindow] = None
component_combo: Optional[Gtk.ComboBoxText] = None
status_online: Optional[Gtk.RadioButton] = None
status_offline: Optional[Gtk.RadioButton] = None
reconnect_attempts = 0

# Define constants for button labels
SUBMIT_CREATE_LABEL = "Submit create entity request"
SUBMIT_REMOVE_LABEL = "Submit remove entity request"
SUBMIT_GET_LABEL = "Submit get entity request"
SUBMIT_ADD_COMPONENT_LABEL = "Submit add component to entity request"
SHUTDOWN_LABEL = "Shutdown"


def create_window() -> None:
    global window, action_combo, input_box, response_view, response_scroll, status_online, status_offline

    window = Gtk.Window(title="API Tester")
    window.set_border_width(10)
    window.set_default_size(200, 200)
    window.set_resizable(False)

    action_combo = Gtk.ComboBoxText()
    for action in [
        "Create entity",
        "Remove entity",
        "Get entity",
        "Add component to entity",
        "Others",
    ]:
        action_combo.append_text(action)
    action_combo.set_active(0)
    action_combo.connect("changed", on_action_changed)

    input_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    response_view = Gtk.TextView()
    response_view.set_editable(False)
    response_view.set_wrap_mode(Gtk.WrapMode.WORD)
    response_view.override_font(Pango.FontDescription("Menlo 11"))

    response_scroll = Gtk.ScrolledWindow()
    response_scroll.set_vexpand(True)
    response_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
    response_scroll.add(response_view)

    # Create status elements and main layout
    status_label = Gtk.Label(label="Server status")
    status_online = Gtk.RadioButton.new_with_label(None, "Online")
    status_offline = Gtk.RadioButton.new_with_label_from_widget(
        status_online, "Offline"
    )
    status_offline.set_active(True)
    status_online.set_sensitive(False)
    status_offline.set_sensitive(False)

    # Create layout
    status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    status_box.pack_start(status_label, False, False, 0)
    status_box.pack_start(status_online, False, False, 0)
    status_box.pack_start(status_offline, False, False, 0)

    api_label = Gtk.Label(label="API endpoints")
    api_label.set_halign(Gtk.Align.START)

    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    main_box.pack_start(status_box, False, False, 0)
    main_box.pack_start(
        Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
    )
    main_box.pack_start(api_label, False, False, 0)
    main_box.pack_start(action_combo, False, False, 0)
    main_box.pack_start(input_box, True, True, 0)
    main_box.pack_start(
        Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
    )
    main_box.pack_start(response_scroll, True, True, 0)

    window.add(main_box)

    # Initial setup
    on_action_changed(action_combo)
    setup_websocket()

    # Connect window destroy event
    window.connect("destroy", on_destroy)

    # Start connection check timer
    GLib.timeout_add(1000, check_connection_status)


def setup_websocket() -> None:
    try:
        sio.connect(BASE_URL)
        status_online.set_active(True)
        status_offline.set_active(False)
    except Exception:
        status_online.set_active(False)
        status_offline.set_active(True)

    sio.on("status_response", update_status_indicator)
    sio.on("disconnect", on_disconnect)
    sio.on("connect", on_connect)
    sio.on("connect_error", on_connect_error)
    sio.on("reconnect", on_reconnect)
    sio.on("reconnect_attempt", on_reconnect_attempt)

    if sio.connected:
        request_status()
    else:
        logger.warning("WebSocket is not connected at startup")


def on_action_changed(combo: Gtk.ComboBoxText) -> None:
    action = combo.get_active_text()
    clear_input_fields()

    action_map = {
        "Create entity": setup_create_entity_fields,
        "Remove entity": setup_remove_entity_fields,
        "Get entity": setup_get_entity_fields,
        "Add component to entity": setup_add_component_to_entity_fields,
        "Others": setup_others_fields,
    }

    action_map.get(action, lambda: None)()  # Call the corresponding setup function
    window.show_all()


def setup_create_entity_fields() -> None:
    add_input_field("Name")
    add_input_field("Target scene")
    add_input_field("Tags (comma-separated)")
    add_submit_button(SUBMIT_CREATE_LABEL, on_create_entity)


def setup_remove_entity_fields() -> None:
    add_input_field("Entity ID")
    add_submit_button(SUBMIT_REMOVE_LABEL, on_remove_entity)


def setup_get_entity_fields() -> None:
    add_input_field("Entity ID")
    add_submit_button(SUBMIT_GET_LABEL, on_get_entity)


def setup_add_component_to_entity_fields() -> None:
    global component_combo
    add_input_field("Entity ID")
    component_combo = Gtk.ComboBoxText()
    component_combo.append_text("Transform")
    component_combo.set_active(0)
    component_combo.connect("changed", on_component_changed)
    input_box.pack_start(component_combo, False, False, 0)
    add_submit_button(SUBMIT_ADD_COMPONENT_LABEL, on_add_component_to_entity)
    on_component_changed(component_combo)


def on_component_changed(combo: Gtk.ComboBoxText) -> None:
    clear_transform_fields()
    if combo.get_active_text() == "Transform":
        add_transform_fields()


def add_transform_fields() -> None:
    for field in ["Position", "Rotation", "Scale"]:
        add_input_field(field)


def clear_transform_fields() -> None:
    for label_text in ["Position", "Rotation", "Scale"]:
        if label_text in entry_fields:
            entry = entry_fields[label_text]
            input_box.remove(entry.get_parent())
            del entry_fields[label_text]


def setup_others_fields() -> None:
    add_others_buttons()
    clear_submit_button()


def add_input_field(label_text: str) -> Gtk.Entry:
    label = Gtk.Label(label=label_text)
    label.set_halign(Gtk.Align.START)
    entry = Gtk.Entry()
    input_box.pack_start(label, False, False, 0)
    input_box.pack_start(entry, False, False, 0)
    entry_fields[label_text] = entry
    return entry


def add_submit_button(button_label: str, callback) -> None:
    clear_submit_button()
    submit_button = Gtk.Button(label=button_label)
    submit_button.connect("clicked", callback)
    input_box.pack_start(submit_button, False, False, 0)


def clear_submit_button() -> None:
    for widget in input_box.get_children():
        if isinstance(widget, Gtk.Button) and widget.get_label().startswith("Submit"):
            input_box.remove(widget)


def add_others_buttons() -> None:
    shutdown_button = Gtk.Button(label=SHUTDOWN_LABEL)
    shutdown_button.connect("clicked", on_shutdown)
    input_box.pack_start(shutdown_button, False, False, 0)


def clear_input_fields() -> None:
    for widget in input_box.get_children():
        if isinstance(widget, (Gtk.Label, Gtk.Entry, Gtk.ComboBoxText)):
            input_box.remove(widget)
    entry_fields.clear()


def on_create_entity(button: Gtk.Button) -> None:
    data = {
        "name": entry_fields["Name"].get_text(),
        "targetScene": entry_fields["Target scene"].get_text(),
        "tags": entry_fields["Tags (comma-separated)"].get_text().split(","),
    }
    try:
        response = requests.post(f"{BASE_URL}/create_entity", json=data)
        response.raise_for_status()  # Raise an error for bad responses
        display_response(response.json())
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating entity: {e}")
        display_response({"status": "error", "reason": str(e)})


def on_remove_entity(button: Gtk.Button) -> None:
    entity_id = entry_fields["Entity ID"].get_text()
    response = requests.delete(f"{BASE_URL}/remove_entity/{entity_id}")
    display_response(response.json())


def on_get_entity(button: Gtk.Button) -> None:
    entity_id = entry_fields["Entity ID"].get_text()
    response = requests.get(f"{BASE_URL}/get_entity/{entity_id}")
    display_response(response.json())


def on_shutdown(button):
    response = requests.post(f"{BASE_URL}/shutdown")
    display_response(response.json())


def on_add_component_to_entity(button):
    entity_id = entry_fields["Entity ID"].get_text()
    component_type = component_combo.get_active_text()

    if component_type == "Transform":
        position = entry_fields["Position"].get_text().split(",")
        rotation = entry_fields["Rotation"].get_text().split(",")
        scale = entry_fields["Scale"].get_text().split(",")

        fields = {"Position": position, "Rotation": rotation, "Scale": scale}
        if not all(
            all(coordinate.replace(".", "", 1).isdigit() for coordinate in coords)
            for coords in fields.values()
        ):
            for label, coords in fields.items():
                if not all(
                    coordinate.replace(".", "", 1).isdigit() for coordinate in coords
                ):
                    highlight_label(label)
            return

        try:
            position = [float(coordinate) for coordinate in position]
            rotation = [float(coordinate) for coordinate in rotation]
            scale = [float(coordinate) for coordinate in scale]
            clear_highlight()
        except ValueError:
            return

        data = {
            "type": "transform",
            "data": {"position": position, "rotation": rotation, "scale": scale},
        }
    else:
        logger.error("Invalid component type")
        return

    response = requests.post(
        f"{BASE_URL}/add_component_to_entity/{entity_id}", json=data
    )
    if response.status_code != 200:
        display_response(response.json())
        return

    display_response(response.json())


def display_response(response_data):
    GLib.idle_add(_update_response_view, response_data)


def _update_response_view(response_data):
    response_view.get_buffer().set_text("")
    response_str = str(response_data)
    response_view.get_buffer().insert_at_cursor(response_str)
    return False


def highlight_label(label_text):
    if label_text in entry_fields:
        label = input_box.get_children()[
            input_box.get_children().index(entry_fields[label_text]) - 1
        ]
        label.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(1, 0, 0, 1))


def clear_highlight():
    for label_text in ["Position", "Rotation", "Scale"]:
        if label_text in entry_fields:
            label = input_box.get_children()[
                input_box.get_children().index(entry_fields[label_text]) - 1
            ]
            label.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 0, 0, 1))


def update_status_indicator(data):
    if data["status"] == "success":
        status_online.set_active(True)
        status_offline.set_active(False)
    else:
        status_online.set_active(False)
        status_offline.set_active(True)


def request_status():
    if sio.connected:
        sio.emit("request_status")


def on_connect():
    status_online.set_active(True)
    status_offline.set_active(False)
    request_status()


def on_disconnect():
    status_online.set_active(False)
    status_offline.set_active(True)
    GLib.timeout_add(1000, try_reconnect)


def try_reconnect():
    global reconnect_attempts
    if sio.connected:
        reconnect_attempts = 0
        on_connect()
        return False

    try:
        sio.connect(BASE_URL)
        reconnect_attempts = 0
        sio.on("connect", on_connect)
        return False
    except Exception:
        reconnect_attempts += 1
        wait_time = min(60, 2**reconnect_attempts)
        GLib.timeout_add(wait_time * 1000, try_reconnect)
        return True


def on_connect_error(data):
    status_online.set_active(False)
    status_offline.set_active(True)


def on_reconnect(*args):
    request_status()


def on_reconnect_attempt(*args):
    pass


def on_destroy(widget):
    sio.disconnect()
    Gtk.main_quit()


def check_connection_status():
    if not sio.connected:
        try:
            sio.connect(BASE_URL)
            on_connect()
        except Exception:
            pass
    return True


def main():
    create_window()
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
