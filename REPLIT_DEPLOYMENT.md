# Replit deployment

ICE is a stateful PDF/XML workspace. Use a **Reserved VM web server** deployment with one instance so active uploads, background PDF processing, and exports use the same process and data directory.

## Import and publish

1. Import `infinitypvtltd8/ice_agents` from GitHub into Replit.
2. Add a Replit **deployment secret** named `ICE_ACCESS_PASSWORD` with a randomly generated value of at least 24 characters. Do not put this value in the repository or `.replit` file. The shared password is used by all four account names: `AP01`, `AP02`, `AP03`, and `ST022`.
3. Publish as a **Reserved VM** web server. Keep the single port mapping at internal port 5000 to external port 80.
4. Use the deployed `https://<app-name>.replit.app` URL. The browser will ask for a username and password. Enter one of the four account names above and the same shared secret as the password. Share the secret only with the people allowed to edit and export the workspace.

The deployment is protected with HTTP Basic authentication before the UI or any API route is served. Public binding without the required secret fails at startup. Replit's private-deployment access control can be enabled as an additional layer where the account plan supports it.

## Data handling

All four accounts share one password and one workspace; they can all read, edit, clear, and export its records. The account name is recorded in the session, but this deployment does not provide per-user permissions or workspaces. Download XML exports promptly. Job state and uploaded source files are written under `ICE_Local/data/` on the VM; treat redeploys, restarts, and deletion of the Repl as potential data loss. This deployment does not provide a durable external archive.

The application has no outbound network calls during document processing. The XML/PDF files and review notes are available to anyone who has the shared workspace password.
