# Installation

cd /<your_workdir>/mono
docker build -t account:1 . -f account/Dockerfile
cd account
docker compose down --remove-orphans && docker compose up
if alembic/versions is empty:
    docker compose exec account sh -c "cd ../ && alembic  revision --autogenerate -m 'init migration'"
docker compose exec account sh -c "cd ../ && alembic upgrade head"
open http://<your_host_or_ip>:8070/docs#
