# Nginx rate limiting

Use Nginx to enforce burst controls on login and checkout endpoints.

```nginx
limit_req_zone $binary_remote_addr zone=login_zone:10m rate=10r/s;

server {
  location /login {
    limit_req zone=login_zone burst=20 nodelay;
    proxy_pass http://app_upstream;
  }
}
```

## Verify

- Watch the 429 rate in Security Events.
- Ensure legitimate logins still succeed.
