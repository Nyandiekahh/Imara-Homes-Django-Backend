# Database ERD

Preview this file in VS Code Markdown to render the ER diagram.

```mermaid
erDiagram
    USER {
        uuid id PK
        string email
        string full_name
        string role
    }

    PROPERTY {
        uuid id PK
        uuid owner_id FK
        string name
        string type
    }

    PROPERTY_AGENT {
        uuid id PK
        uuid property_id FK
        uuid agent_id FK
        uuid assigned_by_id FK
    }

    UNIT {
        uuid id PK
        uuid property_id FK
        string name
        string unit_type
    }

    PAYMENT_CONFIG {
        uuid id PK
        uuid property_id FK
        int due_day
        string fine_type
    }

    PROPERTY_DOCUMENT {
        uuid id PK
        uuid property_id FK
        uuid uploaded_by_id FK
        string document_type
    }

    TENANCY {
        uuid id PK
        uuid user_id FK
        uuid property_id FK
        uuid unit_id FK
        uuid invited_by_id FK
        string status
    }

    TENANT_RATING {
        uuid id PK
        uuid tenancy_id FK
        uuid rated_by_id FK
        int rating
    }

    LEASE {
        uuid id PK
        uuid tenancy_id FK
        uuid property_id FK
        uuid unit_id FK
        string status
    }

    MAINTENANCE_REQUEST {
        uuid id PK
        uuid tenancy_id FK
        uuid unit_id FK
        uuid assigned_to_id FK
        string status
        string priority
    }

    MAINTENANCE_ATTACHMENT {
        uuid id PK
        uuid request_id FK
        uuid uploaded_by_id FK
    }

    PAYMENT {
        uuid id PK
        uuid tenancy_id FK
        uuid property_id FK
        uuid unit_id FK
        string status
        string payment_method
    }

    MPESA_TRANSACTION {
        uuid id PK
        uuid payment_id FK
        string checkout_request_id
    }

    ANNOUNCEMENT {
        uuid id PK
        uuid sender_id FK
        uuid property_id FK
        string type
        string status
    }

    NOTICE {
        uuid id PK
        uuid tenant_id FK
        uuid property_id FK
        string type
        bool is_read
    }

    EMAIL_LOG {
        uuid id PK
        uuid announcement_id FK
        string recipient_email
        string status
    }

    SMS_LOG {
        uuid id PK
        uuid announcement_id FK
        string recipient_phone
        string status
    }

    EMAIL_TEMPLATE {
        uuid id PK
        string name
        bool is_active
    }

    OTP_CODE {
        uuid id PK
        uuid user_id FK
        string purpose
        string code
    }

    USER ||--o{ PROPERTY : owns
    USER ||--o{ PROPERTY_AGENT : agent_assignments
    USER ||--o{ PROPERTY_AGENT : agent_assignments_made
    PROPERTY ||--o{ PROPERTY_AGENT : has_agents
    PROPERTY ||--o| PAYMENT_CONFIG : payment_config
    PROPERTY ||--o{ UNIT : has_units
    PROPERTY ||--o{ PROPERTY_DOCUMENT : documents
    USER ||--o{ PROPERTY_DOCUMENT : uploads
    USER ||--o| TENANCY : tenancy_profile
    USER ||--o{ TENANCY : tenant_invites
    PROPERTY ||--o{ TENANCY : tenancies
    UNIT ||--o{ TENANCY : tenancies
    TENANCY ||--o{ TENANT_RATING : ratings
    USER ||--o{ TENANT_RATING : ratings_given
    TENANCY ||--o{ LEASE : leases
    PROPERTY ||--o{ LEASE : leases
    UNIT ||--o{ LEASE : leases
    TENANCY ||--o{ MAINTENANCE_REQUEST : maintenance_requests
    UNIT ||--o{ MAINTENANCE_REQUEST : maintenance_requests
    USER ||--o{ MAINTENANCE_REQUEST : assigned_maintenance_requests
    MAINTENANCE_REQUEST ||--o{ MAINTENANCE_ATTACHMENT : attachments
    USER ||--o{ MAINTENANCE_ATTACHMENT : maintenance_photos
    TENANCY ||--o{ PAYMENT : payments
    PROPERTY ||--o{ PAYMENT : payments
    UNIT ||--o{ PAYMENT : payments
    PAYMENT ||--|| MPESA_TRANSACTION : mpesa_transaction
    USER ||--o{ ANNOUNCEMENT : sent_announcements
    PROPERTY ||--o{ ANNOUNCEMENT : announcements
    USER ||--o{ NOTICE : notices
    PROPERTY ||--o{ NOTICE : notices
    ANNOUNCEMENT ||--o{ EMAIL_LOG : email_logs
    ANNOUNCEMENT ||--o{ SMS_LOG : sms_logs
    USER ||--o{ OTP_CODE : otp_codes
```

## Quick read

- `PROPERTY` is the hub for units, tenancies, leases, payments, documents, and announcements.
- `TENANCY` connects a tenant user to a property and optionally a unit.
- `LEASE`, `PAYMENT`, and `MAINTENANCE_REQUEST` all hang off the tenancy and often also reference the property and unit.
- `ANNOUNCEMENT` is the parent for both email and SMS delivery logs.
- `MPESA_TRANSACTION` is a one-to-one extension of `PAYMENT`.