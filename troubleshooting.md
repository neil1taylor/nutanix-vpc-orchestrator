# Troublshooting

## Run the setup script

`setup.sh` is run during the cloud-int stage via `deploy.sh` but can be run again. Some things will fail as they have been configured

1. SSH to the pxe server

```bash
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
`setup.sh` logs to `/var/log/nutanix-pxe-setup.log`


## Manualy run the app

```bash
sudo systemctl stop nutanix-pxe
sudo -u nutanix ./venv/bin/python app.py
```