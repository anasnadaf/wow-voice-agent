# certs/

Gitignored TLS + auth material. Place here on the host:

- `origin.pem` / `origin-key.pem` — Cloudflare origin certificate for
  `*.anasnadaf.com` (Cloudflare dashboard → SSL/TLS → Origin Server →
  Create Certificate). Pair with SSL mode **Full (strict)**.
- `htpasswd` — basic-auth file for wowlogs.anasnadaf.com:
  `htpasswd -cB certs/htpasswd <user>` (or
  `docker run --rm httpd:alpine htpasswd -nbB <user> '<pass>' > certs/htpasswd`).
