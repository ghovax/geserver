import gi
import requests
from gi.repository import Gtk, Pango, GLib

gi.require_version("Gtk", "3.0")

# Define a constant for the base URL
BASE_URL = "http://localhost:5001"


class APIGUI(Gtk.Window):
    def __init__(self):
        super().__init__(title="API Tester")
        self.set_border_width(10)
        self.set_default_size(400, 400)

        self.action_combo = Gtk.ComboBoxText()
        self.action_combo.append_text("Create entity")
        self.action_combo.append_text("Remove entity")
        self.action_combo.append_text("Get entity")
        self.action_combo.append_text("Add component")
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

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.pack_start(self.action_combo, False, False, 0)
        main_box.pack_start(self.input_box, True, True, 0)
        main_box.pack_start(self.response_scroll, True, True, 0)
        self.add(main_box)

    def on_action_changed(self, combo):
        action = combo.get_active_text()
        self.clear_input_fields()

        if action == "Create entity":
            self.setup_create_entity_fields()
        elif action == "Remove entity":
            self.setup_remove_entity_fields()
        elif action == "Get entity":
            self.setup_get_entity_fields()
        elif action == "Add component":
            self.setup_add_component_fields()
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

    def setup_add_component_fields(self):
        self.add_input_field("Entity ID")
        self.component_combo = Gtk.ComboBoxText()
        self.component_combo.append_text("Transform")
        self.component_combo.set_active(0)
        self.component_combo.connect("changed", self.on_component_changed)
        self.input_box.pack_start(self.component_combo, False, False, 0)
        self.add_submit_button("Submit add component request", self.on_add_component)

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

    def on_add_component(self, button):
        entity_id = self.entry_fields["Entity ID"].get_text()
        component_type = self.component_combo.get_active_text()

        # Gather data for the Transform component
        if component_type == "Transform":
            position = self.entry_fields["Position"].get_text().split(",")
            rotation = self.entry_fields["Rotation"].get_text().split(",")
            scale = self.entry_fields["Scale"].get_text().split(",")

            # Convert string inputs to float
            try:
                position = [float(coordinate) for coordinate in position]
                rotation = [float(coordinate) for coordinate in rotation]
                scale = [float(coordinate) for coordinate in scale]
            except ValueError:
                self.display_response(
                    {
                        "status": "error",
                        "message": "Invalid input for position, rotation, or scale",
                    }
                )
                return

            data = {
                "type": "transform",
                "data": {"position": position, "rotation": rotation, "scale": scale},
            }
        else:
            self.display_response(
                {"status": "error", "message": "Unsupported component type"}
            )
            return

        # Send the request to the server
        response = requests.post(f"{BASE_URL}/add_component/{entity_id}", json=data)

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


if __name__ == "__main__":
    window = APIGUI()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
