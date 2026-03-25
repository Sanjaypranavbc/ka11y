docker rm -f $(docker ps -aq)
docker volume prune -f
docker network prune -f

#restart docker in linux
sudo systemctl restart docker

#docker compose down and up
docker compose down -v
docker compose up --build
#docker compose build --parallel
#docker compose up -d