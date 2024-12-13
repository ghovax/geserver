import unittest
from server.api import flask_app


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.app = flask_app.test_client()
        self.app.testing = True
        self.reset_server()

    def reset_server(self):
        response = self.app.post("/reset")
        self.assertEqual(response.status_code, 200, "Failed to reset the server")

    def test_create_entity_invalid_inputs(self):
        # Test creating an entity with various invalid inputs
        invalid_cases = [
            {"name": "", "targetScene": "Test Scene"},  # Empty name
            {"name": "Test Entity"},  # Missing targetScene
            {},  # Missing both
            {"name": "Test Entity", "targetScene": ""},  # Empty targetScene
        ]
        for case in invalid_cases:
            response = self.app.post("/create_entity", json=case)
            self.assertEqual(
                response.status_code,
                400,
                f"{case} should return 400, but returned {response.get_json()}",
            )

    def test_add_component_invalid_inputs(self):
        # Test adding a component with various invalid inputs
        invalid_cases = [
            {
                "data": {
                    "position": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                }
            },  # Missing type
            {
                "type": "invalid_type",
                "data": {
                    "position": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
            },  # Invalid type
            {"type": "transform", "data": {}},  # Empty data
            {
                "type": "transform",
                "data": {
                    "position": [1e7, 1e7, 1e7],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
            },  # Excessive scale values
            {
                "type": "transform",
                "data": {
                    "position": ["not", "a", "number"],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
            },  # Non-numeric position
        ]
        for case in invalid_cases:
            response = self.app.post(
                "/add_component_to_entity", json={"entityId": 1, **case}
            )
            self.assertEqual(response.status_code, 400)

    def test_remove_entity_twice(self):
        # First removal
        response = self.app.delete("/remove_entity", json={"entityId": 1})
        self.assertEqual(
            response.status_code, 404
        )  # Should be 404 since it doesn't exist

        # Attempt to remove again
        response = self.app.delete("/remove_entity", json={"entityId": 1})
        self.assertEqual(response.status_code, 404)  # Should still be 404

    def test_add_component_to_nonexistent_entity(self):
        response = self.app.post(
            "/add_component_to_entity",
            json={
                "entityId": 999999,
                "type": "transform",
                "data": {
                    "position": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_create_entity_with_invalid_json(self):
        response = self.app.post("/create_entity", data="invalid json")
        self.assertEqual(response.status_code, 415)

    def test_full_entity_lifecycle(self):
        # Create entity
        create_response = self.app.post(
            "/create_entity",
            json={
                "name": "Lifecycle Test",
                "targetScene": "Test Scene",
                "tags": ["test", "lifecycle"],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        entity_id = create_response.get_json()["data"]["entityId"]

        # Add component
        add_component_response = self.app.post(
            "/add_component_to_entity",
            json={
                "entityId": entity_id,
                "type": "transform",
                "data": {
                    "position": [1.0, 2.0, 3.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
            },
        )
        self.assertEqual(add_component_response.status_code, 200)

        # Get entity components
        get_response = self.app.get(
            f"/get_entity_components", json={"entityId": entity_id}
        )
        self.assertEqual(get_response.status_code, 200)
        entity_data = get_response.get_json()["data"]
        self.assertEqual(
            entity_data["components"]["Transform"]["position"], [1.0, 2.0, 3.0]
        )

        # Remove entity
        remove_response = self.app.delete(
            f"/remove_entity", json={"entityId": entity_id}
        )
        self.assertEqual(remove_response.status_code, 200)

        # Verify entity is gone
        get_response_after = self.app.get(
            f"/get_entity_components", json={"entityId": entity_id}
        )
        self.assertEqual(get_response_after.status_code, 404)

    def test_reset_server_state(self):
        response = self.app.post("/reset")
        self.assertEqual(response.status_code, 200)  # Ensure reset works