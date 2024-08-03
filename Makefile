# Development
dev:
	docker-compose up

# Build
build:
	docker-compose build

# Build
build-prod:
	docker-compose -f docker-compose.prod.yml build

# Production
prod:
	docker-compose -f docker-compose.prod.yml up -d

# Stop and remove containers
down:
	docker-compose down
	docker-compose -f docker-compose.prod.yml down

# Enter the shell of the Django container
shell-web:
	docker exec -it django_app /bin/bash

# Enter the shell of the admin bot container
shell-admin:
	docker exec -it admin_bot /bin/bash

# Enter the shell of the reservation bot container
shell-reservation:
	docker exec -it reservation_bot /bin/bash