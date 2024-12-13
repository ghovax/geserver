rotating_cube:
	python -m server.main &
	echo "Waiting for server to start..."

	sleep 2
	curl -X POST http://localhost:5001/create_entity \
	-H "Content-Type: application/json" \
	-d '{"name": "CubeEntity", "targetScene": "MainScene", "tags": ["cube"]}'

	curl -X POST http://localhost:5001/add_component_to_entity \
	-H "Content-Type: application/json" \
	-d '{"entityId": 1, "type": "script", "data": {"scriptPath": "/Users/giovannigravili/geserver/custom_scripts/my_custom_script.py"}}'

	sleep 5
	echo "Removing entity..."

	curl -X DELETE http://localhost:5001/remove_entity -H "Content-Type: application/json" -d '{"entityId": 1}'

configure_environment:
	python3 -m venv venv
	source venv/bin/activate
	pip install -r requirements.txt
