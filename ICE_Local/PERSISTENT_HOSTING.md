# ICE Local on a persistent free-tier VM

The Vercel Hobby runtime is serverless and does not preserve the app's local
job files. This deployment keeps the existing Python server and its background
queue on a VM with a persistent Docker volume. The container setup is portable
to any Linux VM that provides Docker Compose, a stable public address, and a
hostname for HTTPS.

## Free-tier option: Oracle Cloud Always Free

Oracle currently lists Always Free compute and 200 GB total block-volume
storage for eligible accounts. Availability depends on the account's home
region and VM capacity. Keep the VM, boot volume, and network resources inside
the Always Free allocations shown in the OCI console; do not upgrade the
account or create trial-only resources if the requirement is zero charges.
Oracle signup may require a payment card for identity verification, although
its signup guide says the card is not charged unless the account is upgraded.
Oracle also says an Always Free VM may be reclaimed when CPU, network, and
(for A1) memory utilization all remain below its thresholds over a 7-day
window. Keep an independent backup of the data volume; this free option does
not provide a production uptime guarantee.

Official details: [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[Free Tier signup guide](https://docs.oracle.com/en/learn/cloud_free_tier/).

## Prepare the VM

1. Create an eligible Linux VM in the tenancy's home region. The app is CPU
   intensive during PDF extraction; the Always Free Ampere allocation can
   provide up to 2 OCPUs and 12 GB of memory. Confirm the image architecture is
   ARM64 or AMD64 and that all selected resources are labeled Always Free.
2. Configure the VM firewall/security list to allow SSH from your address and
   inbound TCP 80 and 443. Do not expose port 8080; the reverse proxy is the
   only public entry point.
3. Point a DNS hostname you control to the VM's public IP. Caddy will obtain
   and renew an HTTPS certificate for that hostname.
4. Install Docker Engine and the Docker Compose plugin on the VM.
5. Clone the repository and enter `ICE_Local`:

   ```sh
   git clone https://github.com/infinitypvtltd8/ice_agents.git
   cd ice_agents/ICE_Local
   ```

6. Create a server-only `.env` file. Use one password for the four logins
   `AP01`, `AP02`, `AP03`, and `ST022`; make it at least 24 characters. Never
   commit this file or paste the password into chat.

   ```sh
   cat > .env <<'EOF'
   ICE_DOMAIN=ice.example.com
   ICE_ACCESS_PASSWORD=replace-with-a-random-secret-at-least-24-characters
   EOF
   chmod 600 .env
   ```

7. Start the service:

   ```sh
   docker compose up -d --build
   docker compose ps
   docker compose logs --tail=100 ice caddy
   ```

Open `https://ice.example.com`. The browser will prompt for Basic Auth. Enter
one of the four usernames and the shared password. The `ice-data` Docker volume
persists source packages, metadata, XML, history, and exports across container
restarts. The app's Clear control removes selected saved work. Back up the
volume before VM maintenance.

## Updating the app

From `ICE_Local` on the VM:

```sh
git pull --ff-only
docker compose up -d --build
```

The container uses the same deterministic parser and rule engine as the local
app. It does not send PDFs or metadata to an AI service.

## Operational limits

- Free VM capacity is not guaranteed in every region. OCI may require account
  verification and a valid card at signup. Check the Always Free labels before
  creating resources; the deployment has not been provisioned by this repo.
  Oracle may reclaim Always Free VMs that remain idle by its 7-day criteria, so
  keep a separate backup of saved article data and do not treat this as an SLA.
- The shared password is the same for all four usernames. Change it by editing
  `.env` on the VM and running `docker compose up -d`.
- Protect SSH, keep the VM patched, and retain a separate backup of `/data`.
- This repository setup does not create an OCI account, DNS record, public IP,
  VM, or deployment. Those require access to the user's cloud account.
