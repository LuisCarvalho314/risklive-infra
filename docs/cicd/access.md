# Restricted SSH activation

GitHub-hosted runners perform tests/builds. Deployment uses three dedicated SSH keys and three forced-command users. A self-hosted runner would execute repository code on the production host and is unnecessary. Neither account joins the Docker group. The only sudo commands are fixed deployment operations; root-owned scripts validate JSON and use a root-owned policy. One host lock serializes development and production changes.

Do not run provisioning until explicitly approved. Review `scripts/deploy/provision-access.sh`, generate three dedicated Ed25519 keypairs offline, and run as root:

```sh
bash scripts/deploy/provision-access.sh /secure/dev.pub /secure/prod.pub /secure/prod-plan.pub
```

Install reviewed `/etc/risklive-deploy/dev.json` and `prod.json` as root mode 0600. Code, configuration checkouts and parent directories must be root-owned and unwritable by deployment users. Keep runtime API secrets only in existing host environment files. Configure a host-only read credential for private GHCR pulls using Docker's credential store; it needs packages read only, never write. CI publication uses GITHUB_TOKEN. No personal token with repository write access is required.

Create protected GitHub `development`, `production-plan` and `production` environments, restricting branches to reviewed deployment refs. Production requires reviewers, prevents self-review and administrative bypass, and excludes PR refs. Store independent `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`, and `DEPLOY_KNOWN_HOSTS` secrets per environment. Capture the SSH host key directly from the VM console and verify its SHA256 fingerprint out of band; do not trust an unverified runtime ssh-keyscan. Development automatic updates use only development secrets. Live API testing needs a separate reviewed host policy; the ordinary development key cannot enable it.

Verification before activation: `visudo -c`; inspect `id risklive-deploy-dev` and prod (neither may belong to docker); verify root ownership of installed scripts/policies/checkouts; use each key to run `status`; confirm `ssh ... 'id'`, forwarding, a PTY, and cross-environment commands fail. Send a plan before deployment. Check `/var/lib/risklive-deploy` audit/history records and workflow actor/run links. No existing SSH identities or access are removed by provisioning.

The `risklive-deploy-prod-plan` identity can invoke only read-only `plan` and `status`. Its key lives in the `production-plan` GitHub environment so host validation completes before the production environment approval. It cannot pull or start containers.
