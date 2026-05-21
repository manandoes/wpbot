
## wipe the previous session
cd ~/wpbot
docker compose down
docker volume rm wpbot_whatsapp_session wpbot_whatsapp_cache
docker compose up -d


## Start the server, on gcp
sudo su - Dell
gcloud compute ssh wpbot --project=you-tube-automation-493118 --zone=us-central1-a
cd ~/wpbot
bash deploy.sh


## Delete history of specific user
1. get into DB
cd ~/wpbot && docker compose exec postgres psql -U wpbot -d wpbot
2. Delete history
DELETE FROM conversations WHERE phone_number = '919876543210';
3. Reset status
UPDATE contacts SET status = 'not_contacted' WHERE phone_number = '919876543210';
4.Exit:  \q


 