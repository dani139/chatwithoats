# WuzAPI Quick Guide

## Pairing / Login for `chatwithoats` User

**To pair your WhatsApp account with the `chatwithoats` user and see the QR code, visit:**

[http://localhost:8081/login/?token=iamhipster](http://localhost:8081/login/?token=iamhipster)

## `chatwithoats` User Details

*   **User Name**: `chatwithoats`
*   **User Token (for API interaction)**: `iamhipster`
*   **Webhook URL (for receiving events)**: `http://localhost:8000/backend/wuzapi_webhook`

## Admin Operations

**Admin Token** (defined in `docker-compose.dev.yml` for `WUZAPI_ADMIN_TOKEN`):
`UsQSyX7KMf5QNSe1VMgZHqc6RZeXwqn1Tt0UuquKA` (Replace `YOUR_WUZAPI_ADMIN_TOKEN` below with this value)

**Service URL**: `http://localhost:8081`

### 1. Start WuzAPI & its Database

```bash
docker compose -f ../docker-compose.dev.yml up -d wuzapi postgres_wuzapi
```
(Run from the project root directory if `docker-compose.dev.yml` is there, or adjust path accordingly)

### 2. List All Users

```bash
curl -s -X GET -H 'Authorization: YOUR_WUZAPI_ADMIN_TOKEN' http://localhost:8081/admin/users
```

### 3. Add a New User (Example: `chatwithoats`)

```bash
curl -s -X POST -H 'Authorization: YOUR_WUZAPI_ADMIN_TOKEN' -H 'Content-Type: application/json' --data '{"name":"chatwithoats","token":"iamhipster","webhook":"http://localhost:8000/backend/wuzapi_webhook","events":"Message,ReadReceipt"}' http://localhost:8081/admin/users
```
*Response will contain the new user's ID (e.g., `{"id":2}`).*

### 4. Delete a User (Example: User with ID 2)

```bash
curl -s -X DELETE -H 'Authorization: YOUR_WUZAPI_ADMIN_TOKEN' http://localhost:8081/admin/users/2
```

## User-Specific API Usage

Once the `chatwithoats` user is created and paired, you can interact with its specific WhatsApp session (send messages, etc.) using its token (`iamhipster`). Refer to the main WuzAPI project documentation for details on client-specific endpoints (usually prefixed like `/client/{user_name}/...`). 