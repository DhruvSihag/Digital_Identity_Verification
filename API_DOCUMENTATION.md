# OSINT Tool - API Integration Specification

Welcome! This document outlines the exact technical specifications required to integrate your frontend or backend system with our automated OSINT (Open Source Intelligence) Recon API.

Because OSINT scans are resource-intensive and can take 2-10 minutes to complete, this API uses an **Asynchronous Webhook Architecture**.

---

## 1. Connection Details

*   **OSINT API Base URL:** `http://10.5.51.10:8000`
*   **Exact Scan Endpoint:** `POST /api/v1/scan`
*   **Status Endpoint:** `GET /api/v1/status/{job_id}`
*   **API Authentication Format:** Passed via HTTP Headers.
    *   **Header Name:** `X-API-Key`
    *   **Value:** osint-secure-password-123

---

## 2. Execution Rules

*   **Maximum Targets per Request:** 10 targets maximum per batch to prevent AI timeout limits.
*   **Timeout Rules:** The `/api/v1/scan` endpoint will respond within 2 seconds. The actual webhook delivery will occur between 2 and 10 minutes depending on the target complexity.
*   **Rate-Limit Rules:** Maximum 5 concurrent jobs allowed at a time.
*   **Webhook Authentication/Signature:** 
    *   Currently, the system relies on network-level security (e.g., firewall whitelisting). 
    *   Alternatively, you may embed a secure token directly into your `callback_url` (e.g., `https://your-domain.com/webhook?token=YOUR_SECRET_TOKEN`) and validate it when our system POSTs the data.

---

## 3. Initiating a Scan

**Endpoint:** `POST /api/v1/scan`

### Sample Scan Request
```json
{
  "job_id": "JOB00001",
  "targets": ["ad018jan", "john.doe@gmail.com"],
  "callback_url": "https://your-domain.com/api/webhooks/osint-results?token=secure123"
}
```

### Sample Immediate Response (200 OK)
Our server instantly replies with your tracking ID and moves the scraping to a background worker.
```json
{
  "job_id": "JOB00001",
  "status": "processing",
  "message": "Task queued successfully."
}
```

---

## 4. Receiving the Results (The Webhook)

When the OSINT engine finishes scanning, our server will automatically make a `POST` request to the `callback_url` you provided.

### Sample Completed Webhook Payload
```json
{
  "job_id": "JOB00001",
  "status": "completed",
  "results": {
      "inputs_processed": ["ad018jan"],
      
      "username_results": [
         {
             "target": "ad018jan",
             "platform": "Hackerearth",
             "url": "https://hackerearth.com/@ad018jan",
             "status": "Verified Profile Account Located"
         }
      ],
      
      "instagram_results": [
         {
             "target_username": "ad018jan",
             "platform": "Instagram",
             "status": "Target Profile Analysis",
             "extracted_data": {
                 "bio": null,
                 "avatar_url": null,
                 "top_posts": []
             }
         }
      ],
      
      "all_matches": [
         {
             "platform": "Pinterest",
             "url": "https://www.pinterest.com/ad018jan/",
             "enriched_data": {
                 "bio": "Akash prajapat is a professional content creator.",
                 "avatar_url": "https://i.pinimg.com/280x280_RS/...",
                 "local_avatar_path": "avatars/https___www.pinterest.com_ad018jan_.jpg"
             }
         }
      ]
  }
}
```

### Required Webhook Response
When your server receives our payload, your endpoint must return a `200`, `201`, or `202` status code. 

**Important:** Our server uses your successful HTTP status code as the signal to trigger our physical Zero-Footprint File Cleanup process, securely erasing temporary avatar images from our hard drives. If you return a 500 error, our system will assume the transfer failed.
