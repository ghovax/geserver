import gi
import requests
from gi.repository import Gtk, Pango, Gdk
import logging
import socketio
from typing import Optional, Dict
import random
import json

gi.require_version("Gtk", "3.0")

# Load CSS
def load_css():
    css_provider = Gtk.CssProvider()
    css_provider.load_from_path("interface/style.css")  # Load your CSS file
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# Define a constant for the base URL
BASE_URL = "http://localhost:5001"

# Initialize SocketIO client
sio = socketio.Client()

# Global state variables
window: Optional[Gtk.Window] = None
component_combo: Optional[Gtk.ComboBoxText] = None


def create_window() -> None:
    global window
    window = Gtk.Window(title="API Tester")
    window.set_keep_above(True)
    window.set_border_width(10)
    window.set_default_size(1, 1)
    window.set_resizable(False)
    window.set_position(Gtk.WindowPosition.CENTER)

    # Create a drop-down menu for main actions
    action_combo = Gtk.ComboBoxText()
    action_combo.append_text("Create entity")
    action_combo.append_text("Remove entity")
    action_combo.append_text("Get entity")
    action_combo.append_text("Add component to entity")
    action_combo.connect(
        "changed", lambda combo: on_action_selected(combo.get_active_text())
    )

    submit_button = Gtk.Button(label="Execute")
    submit_button.connect(
        "clicked", lambda btn: on_action_selected(action_combo.get_active_text())
    )

    # Layout for main window
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    main_box.pack_start(action_combo, True, True, 0)
    main_box.pack_start(submit_button, True, True, 0)

    window.add(main_box)
    window.connect("destroy", on_destroy)
    window.show_all()
    window.present()
    window.grab_focus()


def on_action_selected(selected_action: str) -> None:
    if selected_action == "Create entity":
        create_entity_window()
    elif selected_action == "Remove entity":
        remove_entity_window()
    elif selected_action == "Get entity":
        get_entity_window()
    elif selected_action == "Add component to entity":
        add_component_window()
    else:
        logger.warning("No valid action selected")


def create_entity_window() -> None:
    entity_window = Gtk.Window(title="Create entity")
    entity_window.set_border_width(10)
    entity_window.set_default_size(1, 1)
    entity_window.set_resizable(False)
    entity_window.move(
        window.get_position()[0] + random.randint(-50, 50),
        window.get_position()[1] + random.randint(-50, 50),
    )

    name_entry = Gtk.Entry()
    target_scene_entry = Gtk.Entry()
    tags_entry = Gtk.Entry()

    submit_button = Gtk.Button(label="Submit")
    submit_button.connect(
        "clicked",
        lambda btn: on_create_entity(name_entry, target_scene_entry, tags_entry),
    )

    # Layout for create entity window
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.pack_start(Gtk.Label(label="Name", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(name_entry, True, True, 0)
    box.pack_start(
        Gtk.Label(label="Target scene", halign=Gtk.Align.START), True, True, 0
    )
    box.pack_start(target_scene_entry, True, True, 0)
    box.pack_start(
        Gtk.Label(label="Tags (comma-separated)", halign=Gtk.Align.START), True, True, 0
    )
    box.pack_start(tags_entry, True, True, 0)
    box.pack_start(submit_button, True, True, 0)

    entity_window.add(box)
    entity_window.show_all()


def on_create_entity(name_entry, target_scene_entry, tags_entry) -> None:
    data = {
        "name": name_entry.get_text(),
        "targetScene": target_scene_entry.get_text(),
        "tags": tags_entry.get_text().split(","),
    }
    try:
        response = requests.post(f"{BASE_URL}/create_entity", json=data)
        response.raise_for_status()
        display_response(response.json())
    except requests.exceptions.RequestException as exception:
        logger.error(f"Error creating entity: {exception}")


def remove_entity_window() -> None:
    entity_window = Gtk.Window(title="Remove entity")
    entity_window.set_border_width(10)
    entity_window.set_default_size(1, 1)
    entity_window.set_resizable(False)
    entity_window.move(
        window.get_position()[0] + random.randint(-50, 50),
        window.get_position()[1] + random.randint(-50, 50),
    )

    entity_id_entry = Gtk.Entry()

    submit_button = Gtk.Button(label="Submit")
    submit_button.connect("clicked", lambda btn: on_remove_entity(entity_id_entry))

    # Layout for remove entity window
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(Gtk.Label(label="Entity ID", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(entity_id_entry, True, True, 0)
    box.pack_start(submit_button, True, True, 0)

    entity_window.add(box)
    entity_window.show_all()


def on_remove_entity(entity_id_entry) -> None:
    entity_id = entity_id_entry.get_text()
    response = requests.delete(f"{BASE_URL}/remove_entity/{entity_id}")
    display_response(response.json())


def get_entity_window() -> None:
    entity_window = Gtk.Window(title="Get entity")
    entity_window.set_border_width(10)
    entity_window.set_default_size(1, 1)
    entity_window.set_resizable(False)
    entity_window.move(
        window.get_position()[0] + random.randint(-50, 50),
        window.get_position()[1] + random.randint(-50, 50),
    )

    entity_id_entry = Gtk.Entry()

    submit_button = Gtk.Button(label="Submit")
    submit_button.connect("clicked", lambda btn: on_get_entity(entity_id_entry))

    # Layout for get entity window
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(Gtk.Label(label="Entity ID", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(entity_id_entry, True, True, 0)
    box.pack_start(submit_button, True, True, 0)

    entity_window.add(box)
    entity_window.show_all()


def on_get_entity(entity_id_entry) -> None:
    entity_id = entity_id_entry.get_text()
    response = requests.get(f"{BASE_URL}/get_entity/{entity_id}")
    display_response(response.json())


def add_component_window() -> None:
    component_window = Gtk.Window(title="Add component to entity")
    component_window.set_border_width(10)
    component_window.set_default_size(1, 1)
    component_window.set_resizable(False)
    component_window.move(
        window.get_position()[0] + random.randint(-50, 50),
        window.get_position()[1] + random.randint(-50, 50),
    )

    # Create a drop-down menu for component types
    component_combo = Gtk.ComboBoxText()
    component_combo.append_text("Transform")
    component_combo.append_text("Script")

    submit_button = Gtk.Button(label="Open")
    submit_button.connect(
        "clicked",
        lambda btn: open_selected_component(component_combo.get_active_text()),
    )

    # Layout for add component window
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(component_combo, True, True, 0)
    box.pack_start(submit_button, True, True, 0)

    component_window.add(box)
    component_window.show_all()


def open_selected_component(selected_component: str) -> None:
    if selected_component == "Transform":
        open_transform_window()
    elif selected_component == "Script":
        open_script_window()
    else:
        logger.warning("No valid component type selected")


def open_transform_window() -> None:
    transform_window = Gtk.Window(title="Add transform component")
    transform_window.set_border_width(10)
    transform_window.set_default_size(1, 1)
    transform_window.set_resizable(False)
    transform_window.move(
        window.get_position()[0] + random.randint(-50, 50),
        window.get_position()[1] + random.randint(-50, 50),
    )

    entity_id_entry = Gtk.Entry()
    
    # Create separate entries for position, rotation, and scale
    position_x_entry = Gtk.Entry()
    position_y_entry = Gtk.Entry()
    position_z_entry = Gtk.Entry()
    
    rotation_x_entry = Gtk.Entry()
    rotation_y_entry = Gtk.Entry()
    rotation_z_entry = Gtk.Entry()
    
    scale_x_entry = Gtk.Entry()
    scale_y_entry = Gtk.Entry()
    scale_z_entry = Gtk.Entry()

    # Set a fixed size for the entry fields
    position_x_entry.set_size_request(15, -1)
    position_y_entry.set_size_request(15, -1)
    position_z_entry.set_size_request(15, -1)
    
    rotation_x_entry.set_size_request(15, -1)
    rotation_y_entry.set_size_request(15, -1)
    rotation_z_entry.set_size_request(15, -1)
    
    scale_x_entry.set_size_request(15, -1)
    scale_y_entry.set_size_request(15, -1)
    scale_z_entry.set_size_request(15, -1)

    submit_button = Gtk.Button(label="Submit")
    submit_button.connect(
        "clicked",
        lambda btn: on_add_transform(
            entity_id_entry, position_x_entry, position_y_entry, position_z_entry,
            rotation_x_entry, rotation_y_entry, rotation_z_entry,
            scale_x_entry, scale_y_entry, scale_z_entry
        ),
    )

    # Layout for transform component window
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(Gtk.Label(label="Entity ID", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(entity_id_entry, True, True, 0)
    
    # Horizontal box for Position
    position_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    position_box.pack_start(position_x_entry, True, True, 0)
    position_box.pack_start(position_y_entry, True, True, 0)
    position_box.pack_start(position_z_entry, True, True, 0)
    box.pack_start(Gtk.Label(label="Position", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(position_box, True, True, 0)

    # Horizontal box for Rotation
    rotation_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    rotation_box.pack_start(rotation_x_entry, True, True, 0)
    rotation_box.pack_start(rotation_y_entry, True, True, 0)
    rotation_box.pack_start(rotation_z_entry, True, True, 0)
    box.pack_start(Gtk.Label(label="Rotation", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(rotation_box, True, True, 0)

    # Horizontal box for Scale
    scale_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    scale_box.pack_start(scale_x_entry, True, True, 0)
    scale_box.pack_start(scale_y_entry, True, True, 0)
    scale_box.pack_start(scale_z_entry, True, True, 0)
    box.pack_start(Gtk.Label(label="Scale", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(scale_box, True, True, 0)

    box.pack_start(submit_button, True, True, 0)

    transform_window.add(box)
    transform_window.show_all()


def open_script_window() -> None:
    script_window = Gtk.Window(title="Add script component")
    script_window.set_border_width(10)
    script_window.set_default_size(1, 1)
    script_window.set_resizable(False)
    script_window.move(
        window.get_position()[0] + random.randint(-50, 50),
        window.get_position()[1] + random.randint(-50, 50),
    )

    entity_id_entry = Gtk.Entry()
    script_path_entry = Gtk.Entry()

    submit_button = Gtk.Button(label="Submit")
    submit_button.connect(
        "clicked", lambda btn: on_add_script(entity_id_entry, script_path_entry)
    )

    # Layout for script component window
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(Gtk.Label(label="Entity ID", halign=Gtk.Align.START), True, True, 0)
    box.pack_start(entity_id_entry, True, True, 0)
    box.pack_start(
        Gtk.Label(label="Script path", halign=Gtk.Align.START), True, True, 0
    )
    box.pack_start(script_path_entry, True, True, 0)
    box.pack_start(submit_button, True, True, 0)

    script_window.add(box)
    script_window.show_all()


def on_add_transform(
    entity_id_entry, position_x_entry, position_y_entry, position_z_entry,
    rotation_x_entry, rotation_y_entry, rotation_z_entry,
    scale_x_entry, scale_y_entry, scale_z_entry
) -> None:
    entity_id = entity_id_entry.get_text()
    position = [
        float(position_x_entry.get_text()),
        float(position_y_entry.get_text()),
        float(position_z_entry.get_text())
    ]
    rotation = [
        float(rotation_x_entry.get_text()),
        float(rotation_y_entry.get_text()),
        float(rotation_z_entry.get_text())
    ]
    scale = [
        float(scale_x_entry.get_text()),
        float(scale_y_entry.get_text()),
        float(scale_z_entry.get_text())
    ]

    data = {
        "type": "transform",
        "data": {
            "position": position,
            "rotation": rotation,
            "scale": scale,
        },
    }

    response = requests.post(
        f"{BASE_URL}/add_component_to_entity/{entity_id}", json=data
    )
    display_response(response.json())


def on_add_script(entity_id_entry, script_path_entry) -> None:
    entity_id = entity_id_entry.get_text()
    script_path = script_path_entry.get_text()

    data = {
        "type": "script",
        "data": {"scriptPath": script_path},
    }

    response = requests.post(
        f"{BASE_URL}/add_component_to_entity/{entity_id}", json=data
    )
    display_response(response.json())


def display_response(response_data):
    # Print response data to the terminal in a pretty format
    logger.info(json.dumps(response_data, indent=4))  # Pretty print JSON


def on_destroy(widget):
    Gtk.main_quit()


def main():
    load_css()  # Load the CSS styles
    create_window()
    Gtk.main()


if __name__ == "__main__":
    main()
