# Troublshooting

## Run the setup script

`setup.sh` is run during the cloud-int stage via `deploy.sh` but can be run again and the output seen on the console as well as `/var/log/nutanix-pxe-setup.log`. When run subsequent times, some things, like the database user, will fail as they have already been configured.

1. SSH to the pxe server

```bash
bash scripts/reset-database.sh
rm -rf /var/log/nutanix-pxe
cd /
GITHUB_REPO="https://github.com/neil1taylor/nutanix-vpc-orchestrator"
GITHUB_BRANCH="main"
PROJECT_DIR="/opt/nutanix-pxe"
rm -rf "$PROJECT_DIR"
git clone --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$PROJECT_DIR"
cd "$PROJECT_DIR"
chmod +x setup.sh
bash setup.sh
```

2. Monitor the install in the console


## Log files

`deploy.sh` logs to `/var/log/nutanix-deployment.log`
`setup.sh` logs to `/var/log/nutanix-pxe-setup.log` tests are logged to `nutanix-pxe-tests.log`
`app.py`, `ibm_cloud_client.py` logs to `/var/log/nutanix-pxe/pxe-server.log`
`nginx` logs to `access.log` and `error.log`
`gunicorn` logs to `/var/log/nutanix-pxe/gunicorn-access.log` and `/var/log/nutanix-pxe/gunicorn-error.log`


## Manualy run the app

```bash
sudo systemctl stop nutanix-pxe
sudo -u nutanix ./venv/bin/python app.py
```

## Test gunicorn manually:
```bash
cd /opt/nutanix-pxe
source /etc/profile.d/app-vars.sh
sudo -u nutanix -E bash -c "source venv/bin/activate && gunicorn --bind 0.0.0.0:8080 --workers 1 app:app"
```

systemctl status nutanix-pxe

tail -n 50 /var/log/nutanix-pxe/gunicorn-error.log