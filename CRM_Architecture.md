# Sports Broadcasting Social Media CRM — Production Architecture Document

**Platform:** Social Media Team CRM for Sports Broadcasting  
**Team Size:** 6 (1 Manager, 5 Executives)  
**Document Version:** 1.0  
**Date:** 2026-06-05  
**Author:** Platform Architecture Specification  

---

## Table of Contents

1. [Tech Stack Recommendation](#section-1-tech-stack-recommendation)
2. [Database Schema](#section-2-database-schema)
3. [Automation Blueprints](#section-3-automation-blueprints)
4. [UI/UX Wireframe Specifications](#section-4-uiux-wireframe-specifications)
5. [Retool Dashboard Component Specs](#section-5-retool-dashboard-component-specs)
6. [Deployment Architecture](#section-6-deployment-architecture)
7. [Implementation Roadmap](#section-7-implementation-roadmap)

---

## SECTION 1: TECH STACK RECOMMENDATION

### 1.1 Options Comparison Matrix

| Criteria | Option A: Airtable + Make + Softr + Twilio | Option B: PostgreSQL + Supabase + Retool + n8n | Option C: Monday.com + Make + Custom Frontend | Option D: ClickUp + Zapier + Custom Portal |
|---|---|---|---|---|
| **Scalability** | Limited (row caps at 50k/base) | Unlimited (PostgreSQL scales horizontally) | Limited (API rate limits, rigid schema) | Moderate (API-dependent) |
| **Monthly Cost (6 users)** | ~$300–450/mo | ~$150–250/mo | ~$400–600/mo | ~$250–400/mo |
| **Microsoft Graph API** | Indirect (via Make webhooks only) | Native (direct REST calls via n8n HTTP nodes) | Indirect (via Make, limited transformations) | Indirect (via Zapier, limited steps) |
| **Real-time Alerts** | Polling only (5-min delay minimum) | Native WebSockets via Supabase Realtime | No native real-time | No native real-time |
| **Design Team Integration** | Softr public pages (basic) | Custom Retool public app or token-based URLs | Manual share links | Manual share links |
| **Custom Automation Logic** | Make scenarios (step-limited) | n8n unlimited workflow logic | Make scenarios (step-limited) | Zapier (task-limited, expensive) |
| **Data Ownership** | Airtable-hosted (vendor lock-in) | Self-hosted Supabase or Supabase Cloud | Monday-hosted | ClickUp-hosted |
| **JSONB / Flexible Fields** | Limited formula fields | Full PostgreSQL JSONB support | No | No |
| **Audit Trail / Logs** | Basic activity log | Full custom logging tables | Limited | Limited |
| **Auth + Row-Level Security** | Airtable permissions only | Supabase RLS (PostgreSQL-native) | Monday permissions | ClickUp permissions |

### 1.2 Detailed Option Analysis

#### Option A: Airtable + Make.com + Softr + Twilio
**Strengths:** Quick to set up, non-technical friendly UI, good for small teams.  
**Weaknesses:** 50,000 row limit per base becomes a constraint within 12 months of live match logging. Make.com webhook handling for Microsoft Graph requires manual polling setup. Softr public pages lack granular token-based access for design tracking. At scale, Airtable API throttling (5 requests/second) creates bottlenecks during live match day bursts.

#### Option B: PostgreSQL + Supabase + Retool + n8n *(Recommended)*
**Strengths:** Full relational database with no row limits. Supabase provides built-in Auth, Row-Level Security, and WebSocket-based Realtime subscriptions. n8n is self-hostable with unlimited workflow executions on the self-hosted plan. Retool offers production-grade dashboard components with SQL-native queries. Microsoft Graph API integrates directly as HTTP nodes in n8n with OAuth2 credential storage.  
**Weaknesses:** Requires initial setup effort (~1–2 days for infra). Retool has per-user licensing on cloud.

#### Option C: Monday.com + Make.com + Custom Frontend
**Strengths:** Familiar project management UI, good Gantt views.  
**Weaknesses:** Expensive at scale ($20–30/user/month base + Make + hosting). Schema is rigid — custom fields in Monday are flat key-value, not relational. Building a custom frontend adds development overhead without the benefits of a proper ORM layer.

#### Option D: ClickUp + Zapier + Custom Portal
**Strengths:** Feature-rich task management with native time tracking.  
**Weaknesses:** Zapier's task-based pricing becomes expensive with high-frequency match-day automation (2,000+ tasks/month). ClickUp API lacks native webhook support for complex conditional logic. Custom portal development cost negates any savings vs. Retool.

### 1.3 Final Recommendation

**Recommended Stack: PostgreSQL (via Supabase) + n8n + Retool + Twilio WhatsApp Business API**

```
┌─────────────────────────────────────────────────────────┐
│                  RECOMMENDED ARCHITECTURE                │
├─────────────────────────────────────────────────────────┤
│  DATABASE LAYER      │  Supabase (PostgreSQL 15)        │
│  AUTH + REALTIME     │  Supabase Auth + Realtime WS     │
│  AUTOMATION ENGINE   │  n8n (self-hosted on Railway)    │
│  DASHBOARD / UI      │  Retool (cloud)                  │
│  NOTIFICATIONS       │  Twilio WhatsApp Business API    │
│  EMAIL INTEGRATION   │  Microsoft Graph API (OAuth2)    │
│  DESIGN TRACKING     │  Retool Public App (token URLs)  │
└─────────────────────────────────────────────────────────┘
```

**Justification by Criterion:**

| Criterion | Justification |
|---|---|
| **Scalability** | PostgreSQL with connection pooling (PgBouncer via Supabase) handles thousands of concurrent rows without additional cost. n8n horizontal scaling via Railway containers. |
| **Cost** | Supabase Pro ($25/mo) + n8n self-hosted ($0 workflow cost) + Retool Team ($10/user/mo = $60/mo) + Twilio ($0.005/message) = ~$135–200/mo total vs. $400+ for alternatives. |
| **Microsoft Graph API** | n8n has a native Microsoft Outlook node with OAuth2 + webhook subscription management. Graph API webhooks push directly to n8n's exposed webhook URL — no polling required. |
| **Real-time Alerts** | Supabase Realtime broadcasts database changes over WebSockets. Retool listens to these events natively. Match day alerts are triggered within milliseconds of DB updates. |
| **Design Team Integration** | Retool public apps with UUID-based tracking tokens allow design team access without requiring CRM accounts. The `tracking_token` field in `design_requests` generates unique, shareable URLs. |

---

## SECTION 2: DATABASE SCHEMA

### 2.1 Entity Relationship Overview

```
users
  ├── series (assigned_to, created_by)
  │     ├── tasks (series_id)
  │     │     ├── design_requests (task_id)
  │     │     ├── publishing_log (task_id)
  │     │     └── email_alerts (task_id)
  │     └── match_days (series_id)
  │           └── notifications (match_day_id)
  ├── tasks (assigned_to, created_by)
  ├── design_requests (requested_by, assigned_designer)
  ├── notifications (user_id)
  ├── publishing_log (logged_by)
  └── analytics_snapshots (user_id)
```

### 2.2 Complete SQL Schema

```sql
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE user_role AS ENUM ('manager', 'executive', 'head', 'design');

CREATE TYPE series_status AS ENUM ('active', 'completed', 'archived');

CREATE TYPE series_priority AS ENUM ('high', 'medium', 'low');

CREATE TYPE task_type AS ENUM (
  'announcement',
  'pre_match',
  'post_match',
  'live_coverage',
  'adhoc'
);

CREATE TYPE task_status AS ENUM (
  'draft',
  'in_progress',
  'pending_approval',
  'approved',
  'published'
);

CREATE TYPE publishing_phase AS ENUM (
  'drafting',
  'content_approved',
  'scheduled_sociality',
  'uploaded_meta',
  'published'
);

CREATE TYPE match_status AS ENUM (
  'scheduled',
  'live',
  'completed',
  'cancelled'
);

CREATE TYPE asset_type AS ENUM (
  'graphic',
  'video_template',
  'story',
  'carousel'
);

CREATE TYPE design_priority AS ENUM ('urgent', 'high', 'medium', 'low');

CREATE TYPE design_status AS ENUM (
  'submitted',
  'in_review',
  'in_progress',
  'revision_requested',
  'completed'
);

CREATE TYPE email_action AS ENUM ('adhoc_created', 'ignored', 'flagged');

CREATE TYPE notification_type AS ENUM (
  'match_alert',
  'task_update',
  'design_update',
  'email_alert'
);

CREATE TYPE notification_priority AS ENUM ('urgent', 'high', 'normal');

CREATE TYPE notification_channel AS ENUM (
  'in_app',
  'slack',
  'whatsapp',
  'push'
);

CREATE TYPE publish_platform AS ENUM (
  'sociality',
  'meta_business',
  'instagram',
  'twitter',
  'facebook'
);

CREATE TYPE publish_status AS ENUM (
  'drafting',
  'scheduled',
  'published',
  'failed'
);

-- ============================================================
-- TABLE 1: users
-- ============================================================
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          VARCHAR(255) NOT NULL,
  role          user_role NOT NULL,
  email         VARCHAR(255) NOT NULL UNIQUE,
  phone         VARCHAR(30),
  avatar_url    TEXT,
  slack_id      VARCHAR(100),
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_email ON users(email);

COMMENT ON TABLE users IS 'Platform users: managers, executives, head of department, design team';
COMMENT ON COLUMN users.slack_id IS 'Slack member ID (Uxxxxxxxxx format) for direct message delivery';

-- ============================================================
-- TABLE 2: series
-- ============================================================
CREATE TABLE series (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title         VARCHAR(500) NOT NULL,
  sport_type    VARCHAR(100) NOT NULL,
  season        VARCHAR(100),
  status        series_status NOT NULL DEFAULT 'active',
  assigned_to   UUID REFERENCES users(id) ON DELETE SET NULL,
  created_by    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  start_date    DATE,
  end_date      DATE,
  description   TEXT,
  priority      series_priority NOT NULL DEFAULT 'medium',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_series_dates CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE INDEX idx_series_status ON series(status);
CREATE INDEX idx_series_assigned_to ON series(assigned_to);
CREATE INDEX idx_series_created_by ON series(created_by);
CREATE INDEX idx_series_sport_type ON series(sport_type);

COMMENT ON TABLE series IS 'A sports series or tournament (e.g., PSL 2026, ICC Champions Trophy)';

-- ============================================================
-- TABLE 3: tasks
-- ============================================================
CREATE TABLE tasks (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  series_id           UUID REFERENCES series(id) ON DELETE SET NULL,
  title               VARCHAR(500) NOT NULL,
  type                task_type NOT NULL,
  status              task_status NOT NULL DEFAULT 'draft',
  assigned_to         UUID REFERENCES users(id) ON DELETE SET NULL,
  created_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  due_date            TIMESTAMPTZ,
  content_copy        TEXT,
  pinterest_refs      JSONB DEFAULT '[]'::jsonb,
  phase_notes         TEXT,
  publishing_status   publishing_phase NOT NULL DEFAULT 'drafting',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tasks_series_id ON tasks(series_id);
CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_type ON tasks(type);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);
CREATE INDEX idx_tasks_created_by ON tasks(created_by);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE tasks IS 'Individual content tasks: announcements, pre/post-match, live coverage, ad hoc';
COMMENT ON COLUMN tasks.pinterest_refs IS 'Array of Pinterest URL objects: [{"url": "...", "label": "..."}]';

-- ============================================================
-- TABLE 4: match_days
-- ============================================================
CREATE TABLE match_days (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  series_id             UUID NOT NULL REFERENCES series(id) ON DELETE CASCADE,
  title                 VARCHAR(500) NOT NULL,
  sport                 VARCHAR(100) NOT NULL,
  teams                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  venue                 VARCHAR(500),
  match_datetime        TIMESTAMPTZ NOT NULL,
  assigned_executive    UUID REFERENCES users(id) ON DELETE SET NULL,
  status                match_status NOT NULL DEFAULT 'scheduled',
  alert_2h_sent         BOOLEAN NOT NULL DEFAULT false,
  alert_1h_sent         BOOLEAN NOT NULL DEFAULT false,
  alert_start_sent      BOOLEAN NOT NULL DEFAULT false,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_match_days_series_id ON match_days(series_id);
CREATE INDEX idx_match_days_match_datetime ON match_days(match_datetime);
CREATE INDEX idx_match_days_status ON match_days(status);
CREATE INDEX idx_match_days_assigned_executive ON match_days(assigned_executive);
-- Composite index for the alert cron query (performance-critical)
CREATE INDEX idx_match_days_alert_query ON match_days(match_datetime, status, alert_2h_sent, alert_1h_sent, alert_start_sent);

COMMENT ON TABLE match_days IS 'Individual match fixtures with automated alert tracking';
COMMENT ON COLUMN match_days.teams IS 'Match teams: {"home": "Team A", "away": "Team B"}';
COMMENT ON COLUMN match_days.alert_2h_sent IS '2-hour pre-match alert sent flag';
COMMENT ON COLUMN match_days.alert_1h_sent IS '1-hour pre-match alert flag';
COMMENT ON COLUMN match_days.alert_start_sent IS 'Match start alert flag';

-- ============================================================
-- TABLE 5: design_requests
-- ============================================================
CREATE TABLE design_requests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id           UUID REFERENCES tasks(id) ON DELETE SET NULL,
  series_id         UUID REFERENCES series(id) ON DELETE SET NULL,
  requested_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  assigned_designer UUID REFERENCES users(id) ON DELETE SET NULL,
  title             VARCHAR(500) NOT NULL,
  description       TEXT,
  pinterest_links   JSONB DEFAULT '[]'::jsonb,
  copy_text         TEXT,
  asset_type        asset_type NOT NULL,
  priority          design_priority NOT NULL DEFAULT 'medium',
  status            design_status NOT NULL DEFAULT 'submitted',
  tracking_token    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
  deadline          TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_design_requests_task_id ON design_requests(task_id);
CREATE INDEX idx_design_requests_series_id ON design_requests(series_id);
CREATE INDEX idx_design_requests_requested_by ON design_requests(requested_by);
CREATE INDEX idx_design_requests_assigned_designer ON design_requests(assigned_designer);
CREATE INDEX idx_design_requests_status ON design_requests(status);
CREATE INDEX idx_design_requests_tracking_token ON design_requests(tracking_token);

COMMENT ON TABLE design_requests IS 'Design asset requests from social media team to design team';
COMMENT ON COLUMN design_requests.tracking_token IS 'UUID used for public tracking URL: /design/{tracking_token}';
COMMENT ON COLUMN design_requests.pinterest_links IS 'Array: [{"url": "...", "label": "Reference 1"}]';

-- ============================================================
-- TABLE 6: email_alerts
-- ============================================================
CREATE TABLE email_alerts (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  outlook_message_id    VARCHAR(500) UNIQUE,
  sender_email          VARCHAR(255) NOT NULL,
  subject               VARCHAR(1000),
  received_at           TIMESTAMPTZ,
  parsed_content        TEXT,
  action_taken          email_action NOT NULL DEFAULT 'flagged',
  task_id               UUID REFERENCES tasks(id) ON DELETE SET NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_email_alerts_sender_email ON email_alerts(sender_email);
CREATE INDEX idx_email_alerts_received_at ON email_alerts(received_at);
CREATE INDEX idx_email_alerts_action_taken ON email_alerts(action_taken);
CREATE INDEX idx_email_alerts_task_id ON email_alerts(task_id);

COMMENT ON TABLE email_alerts IS 'Parsed incoming Outlook emails, linked to auto-created tasks';
COMMENT ON COLUMN email_alerts.outlook_message_id IS 'Microsoft Graph API message ID for deduplication and read-marking';

-- ============================================================
-- TABLE 7: notifications
-- ============================================================
CREATE TABLE notifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type            notification_type NOT NULL,
  title           VARCHAR(500) NOT NULL,
  body            TEXT,
  priority        notification_priority NOT NULL DEFAULT 'normal',
  read            BOOLEAN NOT NULL DEFAULT false,
  match_day_id    UUID REFERENCES match_days(id) ON DELETE SET NULL,
  task_id         UUID REFERENCES tasks(id) ON DELETE SET NULL,
  channel         notification_channel NOT NULL DEFAULT 'in_app',
  sent_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_type ON notifications(type);
CREATE INDEX idx_notifications_read ON notifications(read);
CREATE INDEX idx_notifications_priority ON notifications(priority);
CREATE INDEX idx_notifications_match_day_id ON notifications(match_day_id);
CREATE INDEX idx_notifications_task_id ON notifications(task_id);

COMMENT ON TABLE notifications IS 'All system notifications across channels (in-app, Slack, WhatsApp, push)';

-- ============================================================
-- TABLE 8: publishing_log
-- ============================================================
CREATE TABLE publishing_log (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id           UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  platform          publish_platform NOT NULL,
  status            publish_status NOT NULL DEFAULT 'drafting',
  scheduled_time    TIMESTAMPTZ,
  published_time    TIMESTAMPTZ,
  post_url          TEXT,
  notes             TEXT,
  logged_by         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_publishing_log_task_id ON publishing_log(task_id);
CREATE INDEX idx_publishing_log_platform ON publishing_log(platform);
CREATE INDEX idx_publishing_log_status ON publishing_log(status);
CREATE INDEX idx_publishing_log_scheduled_time ON publishing_log(scheduled_time);

COMMENT ON TABLE publishing_log IS 'Track content publication status across all social platforms';

-- ============================================================
-- TABLE 9: analytics_snapshots
-- ============================================================
CREATE TABLE analytics_snapshots (
  id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_date                 DATE NOT NULL,
  user_id                       UUID REFERENCES users(id) ON DELETE SET NULL,
  total_tasks                   INT NOT NULL DEFAULT 0,
  completed_tasks               INT NOT NULL DEFAULT 0,
  pending_tasks                 INT NOT NULL DEFAULT 0,
  design_requests_completed     INT NOT NULL DEFAULT 0,
  avg_completion_hours          FLOAT,
  live_matches_covered          INT NOT NULL DEFAULT 0,
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_analytics_snapshot UNIQUE (snapshot_date, user_id)
);

CREATE INDEX idx_analytics_snapshots_date ON analytics_snapshots(snapshot_date);
CREATE INDEX idx_analytics_snapshots_user_id ON analytics_snapshots(user_id);

COMMENT ON TABLE analytics_snapshots IS 'Daily aggregated analytics per user or team-wide (user_id NULL = team total)';

-- ============================================================
-- ROW LEVEL SECURITY (Supabase RLS)
-- ============================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE series ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_days ENABLE ROW LEVEL SECURITY;
ALTER TABLE design_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE publishing_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_snapshots ENABLE ROW LEVEL SECURITY;

-- Managers and heads see all; executives see their own + assigned tasks
CREATE POLICY "Users can view their own notifications"
  ON notifications FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Executives see own tasks"
  ON tasks FOR SELECT
  USING (
    assigned_to = auth.uid()
    OR created_by = auth.uid()
    OR EXISTS (
      SELECT 1 FROM users u
      WHERE u.id = auth.uid()
      AND u.role IN ('manager', 'head')
    )
  );

CREATE POLICY "Design team sees submitted requests"
  ON design_requests FOR SELECT
  USING (
    assigned_designer = auth.uid()
    OR requested_by = auth.uid()
    OR EXISTS (
      SELECT 1 FROM users u
      WHERE u.id = auth.uid()
      AND u.role IN ('manager', 'head', 'design')
    )
  );

-- ============================================================
-- USEFUL VIEWS
-- ============================================================

-- Active task summary with assignee name
CREATE VIEW v_active_tasks AS
SELECT
  t.id,
  t.title,
  t.type,
  t.status,
  t.publishing_status,
  t.due_date,
  t.created_at,
  u.name AS assigned_to_name,
  u.role AS assigned_to_role,
  s.title AS series_title,
  s.sport_type
FROM tasks t
LEFT JOIN users u ON t.assigned_to = u.id
LEFT JOIN series s ON t.series_id = s.id
WHERE t.status NOT IN ('published');

-- Upcoming match days in next 24 hours
CREATE VIEW v_upcoming_matches AS
SELECT
  m.id,
  m.title,
  m.sport,
  m.teams,
  m.venue,
  m.match_datetime,
  m.status,
  m.alert_2h_sent,
  m.alert_1h_sent,
  m.alert_start_sent,
  u.name AS assigned_executive_name,
  s.title AS series_title,
  EXTRACT(EPOCH FROM (m.match_datetime - NOW())) / 60 AS minutes_until_match
FROM match_days m
LEFT JOIN users u ON m.assigned_executive = u.id
LEFT JOIN series s ON m.series_id = s.id
WHERE m.match_datetime BETWEEN NOW() AND NOW() + INTERVAL '24 hours'
  AND m.status = 'scheduled'
ORDER BY m.match_datetime ASC;

-- Design request queue with requester info
CREATE VIEW v_design_queue AS
SELECT
  dr.id,
  dr.title,
  dr.asset_type,
  dr.priority,
  dr.status,
  dr.tracking_token,
  dr.deadline,
  dr.pinterest_links,
  dr.copy_text,
  dr.created_at,
  u_req.name AS requested_by_name,
  u_des.name AS assigned_designer_name,
  t.title AS linked_task_title,
  s.title AS series_title
FROM design_requests dr
LEFT JOIN users u_req ON dr.requested_by = u_req.id
LEFT JOIN users u_des ON dr.assigned_designer = u_des.id
LEFT JOIN tasks t ON dr.task_id = t.id
LEFT JOIN series s ON dr.series_id = s.id
WHERE dr.status != 'completed'
ORDER BY
  CASE dr.priority
    WHEN 'urgent' THEN 1
    WHEN 'high' THEN 2
    WHEN 'medium' THEN 3
    WHEN 'low' THEN 4
  END,
  dr.deadline ASC NULLS LAST;
```

### 2.3 JSONB Field Schemas

#### `tasks.pinterest_refs`
```json
[
  {
    "url": "https://pinterest.com/pin/123456",
    "label": "Color palette reference",
    "thumbnail": "https://i.pinimg.com/..."
  }
]
```

#### `match_days.teams`
```json
{
  "home": {
    "name": "Karachi Kings",
    "short": "KK",
    "logo_url": "https://cdn.example.com/kk-logo.png"
  },
  "away": {
    "name": "Lahore Qalandars",
    "short": "LQ",
    "logo_url": "https://cdn.example.com/lq-logo.png"
  }
}
```

#### `design_requests.pinterest_links`
```json
[
  {
    "url": "https://pinterest.com/pin/789",
    "label": "Typography inspiration",
    "notes": "Use this font style for the headline"
  }
]
```

---

## SECTION 3: AUTOMATION BLUEPRINTS

### 3a. Outlook Email Parser (n8n Workflow)

#### Overview
Monitors a designated Outlook mailbox for content updates from the production or content team. Automatically creates adhoc tasks and notifies the manager.

#### Prerequisites
- Microsoft Azure App Registration with `Mail.Read`, `Mail.ReadWrite` permissions
- n8n instance with a publicly accessible webhook URL
- Supabase service role key configured in n8n credentials

#### Step-by-Step Workflow

```
WORKFLOW: outlook_email_parser
Trigger: Microsoft Graph API webhook (push notification)

STEP 1 → Microsoft Graph Webhook Trigger
  - Type: Webhook node (n8n built-in)
  - Endpoint: https://n8n.yourdomain.com/webhook/outlook-parser
  - Validation token: Handled in IF node below

STEP 2 → Validate Webhook Subscription (IF node)
  - Condition: {{ $json.validationToken }} exists
  - TRUE path: Return 200 with validationToken (subscription handshake)
  - FALSE path: Continue to Step 3

STEP 3 → Extract Notification Data (Set node)
  - Fields to set:
    messageId: {{ $json.value[0].resourceData.id }}
    changeType: {{ $json.value[0].changeType }}
    subscriptionId: {{ $json.value[0].subscriptionId }}

STEP 4 → Fetch Full Email (HTTP Request node)
  - Method: GET
  - URL: https://graph.microsoft.com/v1.0/me/messages/{{ $json.messageId }}
  - Auth: OAuth2 (Microsoft account)
  - Headers: { "Content-Type": "application/json" }
  - Query params: $select=subject,body,from,receivedDateTime,isRead

STEP 5 → Filter by Sender (IF node)
  - Condition: {{ $json.from.emailAddress.address }} === "content@yourbroadcaster.com"
    OR {{ $json.subject.toLowerCase().includes("content update") }}
    OR {{ $json.subject.toLowerCase().includes("content sheet") }}
  - FALSE path: → Step 5b (Log as ignored)
  - TRUE path: → Step 6

STEP 5b → Log Ignored Email (Supabase node / HTTP Request)
  - INSERT into email_alerts (action_taken = 'ignored')
  - STOP workflow

STEP 6 → Parse Email Content (Code node - JavaScript)
  ```javascript
  const subject = $input.item.json.subject;
  const bodyHtml = $input.item.json.body.content;
  const bodyText = bodyHtml.replace(/<[^>]*>/g, '').trim();

  // Extract Google Sheets / Drive links
  const linkRegex = /https:\/\/(docs\.google\.com|drive\.google\.com)[^\s"<>]+/g;
  const links = bodyText.match(linkRegex) || [];

  // Extract series/match keywords
  const seriesKeywords = ['PSL', 'ICC', 'Champions Trophy', 'Super League', 'T20'];
  const detectedSeries = seriesKeywords.find(kw =>
    subject.includes(kw) || bodyText.includes(kw)
  ) || null;

  return [{
    json: {
      subject,
      bodyText: bodyText.substring(0, 2000),
      contentLinks: links,
      detectedSeries,
      senderEmail: $input.item.json.from.emailAddress.address,
      receivedAt: $input.item.json.receivedDateTime,
      messageId: $input.item.json.id
    }
  }];
  ```

STEP 7 → Lookup Manager User ID (HTTP Request → Supabase REST)
  - GET /rest/v1/users?role=eq.manager&select=id,name,slack_id
  - Returns manager's UUID and Slack ID

STEP 8 → Create Adhoc Task (HTTP Request → Supabase REST)
  - POST /rest/v1/tasks
  - Body:
    ```json
    {
      "title": "ADHOC: {{ $node['Step 6'].json.subject }}",
      "type": "adhoc",
      "status": "draft",
      "created_by": "{{ $node['Step 7'].json[0].id }}",
      "content_copy": "{{ $node['Step 6'].json.bodyText }}",
      "phase_notes": "Auto-created from Outlook. Links: {{ $node['Step 6'].json.contentLinks.join(', ') }}"
    }
    ```
  - Returns: new task ID

STEP 9 → Log to email_alerts (HTTP Request → Supabase REST)
  - POST /rest/v1/email_alerts
  - Body:
    ```json
    {
      "outlook_message_id": "{{ $node['Step 6'].json.messageId }}",
      "sender_email": "{{ $node['Step 6'].json.senderEmail }}",
      "subject": "{{ $node['Step 6'].json.subject }}",
      "received_at": "{{ $node['Step 6'].json.receivedAt }}",
      "parsed_content": "{{ $node['Step 6'].json.bodyText }}",
      "action_taken": "adhoc_created",
      "task_id": "{{ $node['Step 8'].json.id }}"
    }
    ```

STEP 10 → Create In-App Notification (HTTP Request → Supabase REST)
  - POST /rest/v1/notifications
  - Body:
    ```json
    {
      "user_id": "{{ $node['Step 7'].json[0].id }}",
      "type": "email_alert",
      "title": "New Content Update Email",
      "body": "Email from {{ $node['Step 6'].json.senderEmail }}: {{ $node['Step 6'].json.subject }}",
      "priority": "high",
      "task_id": "{{ $node['Step 8'].json.id }}",
      "channel": "in_app"
    }
    ```

STEP 11 → Send Slack DM to Manager (HTTP Request)
  - POST https://slack.com/api/chat.postMessage
  - Auth: Bearer {{ $credentials.slackToken }}
  - Body:
    ```json
    {
      "channel": "{{ $node['Step 7'].json[0].slack_id }}",
      "text": "📧 *New Content Update Email*\n*From:* {{ $node['Step 6'].json.senderEmail }}\n*Subject:* {{ $node['Step 6'].json.subject }}\n\nAdhoc task has been created. <https://retool.yourdomain.com/tasks/{{ $node['Step 8'].json.id }}|View Task>"
    }
    ```

STEP 12 → Mark Email as Read (HTTP Request → Graph API)
  - PATCH https://graph.microsoft.com/v1.0/me/messages/{{ $node['Step 6'].json.messageId }}
  - Auth: OAuth2 (Microsoft)
  - Body: { "isRead": true }

STEP 13 → END
```

#### n8n Workflow JSON Structure

```json
{
  "name": "Outlook Email Parser",
  "nodes": [
    {
      "name": "Outlook Webhook",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "path": "outlook-parser",
        "responseMode": "responseNode",
        "options": {}
      },
      "position": [200, 300]
    },
    {
      "name": "Validate Subscription",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "string": [{"value1": "={{$json.validationToken}}", "operation": "isNotEmpty"}]
        }
      },
      "position": [400, 300]
    },
    {
      "name": "Return Validation Token",
      "type": "n8n-nodes-base.respondToWebhook",
      "parameters": {
        "respondWith": "text",
        "responseBody": "={{$json.validationToken}}"
      },
      "position": [600, 200]
    },
    {
      "name": "Extract Notification Data",
      "type": "n8n-nodes-base.set",
      "parameters": {
        "values": {
          "string": [
            {"name": "messageId", "value": "={{$json.value[0].resourceData.id}}"},
            {"name": "changeType", "value": "={{$json.value[0].changeType}}"}
          ]
        }
      },
      "position": [600, 400]
    },
    {
      "name": "Fetch Full Email",
      "type": "n8n-nodes-base.microsoftOutlook",
      "parameters": {
        "operation": "get",
        "messageId": "={{$json.messageId}}"
      },
      "position": [800, 400]
    },
    {
      "name": "Filter by Sender",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "string": [
            {
              "value1": "={{$json.from.emailAddress.address}}",
              "operation": "contains",
              "value2": "content@"
            }
          ]
        }
      },
      "position": [1000, 400]
    },
    {
      "name": "Parse Email Content",
      "type": "n8n-nodes-base.code",
      "parameters": {
        "jsCode": "/* See Step 6 JavaScript above */"
      },
      "position": [1200, 400]
    },
    {
      "name": "Create Adhoc Task",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "={{$env.SUPABASE_URL}}/rest/v1/tasks",
        "method": "POST",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth"
      },
      "position": [1400, 400]
    },
    {
      "name": "Log Email Alert",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "={{$env.SUPABASE_URL}}/rest/v1/email_alerts",
        "method": "POST"
      },
      "position": [1600, 300]
    },
    {
      "name": "Notify Manager - In App",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "={{$env.SUPABASE_URL}}/rest/v1/notifications",
        "method": "POST"
      },
      "position": [1600, 400]
    },
    {
      "name": "Notify Manager - Slack",
      "type": "n8n-nodes-base.slack",
      "parameters": {
        "operation": "postMessage",
        "channel": "={{$node['Get Manager'].json[0].slack_id}}"
      },
      "position": [1600, 500]
    },
    {
      "name": "Mark Email Read",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "=https://graph.microsoft.com/v1.0/me/messages/{{$node['Parse Email Content'].json.messageId}}",
        "method": "PATCH",
        "body": "{\"isRead\": true}"
      },
      "position": [1800, 400]
    }
  ],
  "connections": {
    "Outlook Webhook": {"main": [[ {"node": "Validate Subscription"} ]]},
    "Validate Subscription": {
      "main": [
        [{"node": "Return Validation Token"}],
        [{"node": "Extract Notification Data"}]
      ]
    },
    "Extract Notification Data": {"main": [[{"node": "Fetch Full Email"}]]},
    "Fetch Full Email": {"main": [[{"node": "Filter by Sender"}]]},
    "Filter by Sender": {
      "main": [
        [{"node": "Parse Email Content"}],
        [{"node": "Log Ignored Email"}]
      ]
    },
    "Parse Email Content": {"main": [[{"node": "Create Adhoc Task"}]]},
    "Create Adhoc Task": {
      "main": [[
        {"node": "Log Email Alert"},
        {"node": "Notify Manager - In App"},
        {"node": "Notify Manager - Slack"}
      ]]
    },
    "Notify Manager - Slack": {"main": [[{"node": "Mark Email Read"}]]}
  }
}
```

---

### 3b. 3-Tier Match Day Alert Engine (n8n Workflow)

#### Overview
Runs every 5 minutes. Queries upcoming matches, calculates time differences, and fires tiered WhatsApp + Slack + in-app alerts with idempotency flags.

#### Alert Message Templates

**Tier 1 — 2-Hour Alert:**
```
🏏 MATCH ALERT — 2 HOURS TO GO
━━━━━━━━━━━━━━━━━━━━━━━
📅 {{match.title}}
🏟️ {{match.venue}}
⚔️  {{match.teams.home.name}} vs {{match.teams.away.name}}
🕐 Kickoff: {{match.match_datetime | formatDate}}
━━━━━━━━━━━━━━━━━━━━━━━
👤 Assigned: {{executive.name}}
📋 Action: Begin pre-match content prep
```

**Tier 2 — 1-Hour Alert:**
```
⚠️ MATCH ALERT — 1 HOUR TO GO
━━━━━━━━━━━━━━━━━━━━━━━
📅 {{match.title}}
⚔️  {{match.teams.home.name}} vs {{match.teams.away.name}}
🕐 Kickoff in 60 MINUTES
━━━━━━━━━━━━━━━━━━━━━━━
👤 {{executive.name}}: Pre-match graphics should be READY
📌 Confirm Sociality schedule is live
```

**Tier 3 — Match Start Alert:**
```
🚨 MATCH STARTED — GO LIVE NOW
━━━━━━━━━━━━━━━━━━━━━━━
🏟️ {{match.title}} IS LIVE
⚔️  {{match.teams.home.name}} vs {{match.teams.away.name}}
━━━━━━━━━━━━━━━━━━━━━━━
👤 {{executive.name}}: Switch to LIVE COVERAGE mode
📲 Monitor all platforms
🔴 Live score updates: ACTIVATE
```

#### Step-by-Step Workflow

```
WORKFLOW: match_day_alert_engine
Trigger: Cron — every 5 minutes (*/5 * * * *)

STEP 1 → Cron Trigger
  - Schedule: */5 * * * *
  - Timezone: Asia/Karachi (PKT)

STEP 2 → Query Upcoming Matches (HTTP Request → Supabase REST)
  - GET /rest/v1/match_days
  - Query params:
    status=eq.scheduled
    &match_datetime=gte.{{ NOW() }}
    &match_datetime=lte.{{ NOW() + 2.5 hours }}
    &select=*,users!match_days_assigned_executive_fkey(id,name,phone,slack_id)
  - Returns: Array of match objects with executive details

STEP 3 → Check If Any Matches (IF node)
  - Condition: {{ $json.length }} > 0
  - FALSE: Stop workflow (no upcoming matches)
  - TRUE: Continue to Step 4

STEP 4 → Split Into Items (Split In Batches node)
  - Batch Size: 1 (process each match individually)

STEP 5 → Calculate Time Difference (Code node)
  ```javascript
  const match = $input.item.json;
  const matchTime = new Date(match.match_datetime);
  const now = new Date();
  const diffMinutes = Math.floor((matchTime - now) / 60000);

  return [{
    json: {
      ...match,
      diffMinutes,
      should2hAlert: diffMinutes <= 120 && !match.alert_2h_sent,
      should1hAlert: diffMinutes <= 60 && !match.alert_1h_sent,
      shouldStartAlert: diffMinutes <= 0 && !match.alert_start_sent
    }
  }];
  ```

STEP 6 → Route by Alert Tier (Switch node)
  - Route 1: {{ $json.should2hAlert === true }} → 2h Alert Branch
  - Route 2: {{ $json.should1hAlert === true }} → 1h Alert Branch
  - Route 3: {{ $json.shouldStartAlert === true }} → Start Alert Branch
  - Default: No action needed

--- BRANCH: 2-HOUR ALERT ---

STEP 7a → Send WhatsApp Alert (Twilio HTTP Request)
  - POST https://api.twilio.com/2010-04-01/Accounts/{{ACCOUNT_SID}}/Messages
  - Auth: Basic (AccountSID:AuthToken)
  - Body:
    ```
    From: whatsapp:+{{TWILIO_WHATSAPP_NUMBER}}
    To: whatsapp:+{{match.users.phone}}
    Body: [2-Hour Template above]
    ```

STEP 7b → Send Slack Alert (Slack node)
  - channel: {{ $json.users.slack_id }}
  - message: [2-Hour Template as Slack Block Kit]

STEP 7c → Create In-App Notification (HTTP Request → Supabase)
  - POST /rest/v1/notifications
  - Body:
    ```json
    {
      "user_id": "{{ $json.assigned_executive }}",
      "type": "match_alert",
      "title": "Match in 2 Hours: {{ $json.title }}",
      "body": "{{ $json.teams.home.name }} vs {{ $json.teams.away.name }} at {{ $json.venue }}",
      "priority": "high",
      "match_day_id": "{{ $json.id }}",
      "channel": "whatsapp"
    }
    ```

STEP 7d → Update alert_2h_sent Flag (HTTP Request → Supabase)
  - PATCH /rest/v1/match_days?id=eq.{{ $json.id }}
  - Body: { "alert_2h_sent": true }

--- BRANCH: 1-HOUR ALERT ---

STEP 8a → Send WhatsApp Alert (same structure, 1h template)
STEP 8b → Send Slack Alert (1h template)
STEP 8c → Create In-App Notification (priority: "urgent")
STEP 8d → Update alert_1h_sent Flag

--- BRANCH: MATCH START ALERT ---

STEP 9a → Send WhatsApp Alert (MATCH STARTED template)
STEP 9b → Send Slack Alert (MATCH STARTED template, @channel mention)
STEP 9c → Create In-App Notification (priority: "urgent")
STEP 9d → Update match status to 'live' + alert_start_sent flag
  - PATCH /rest/v1/match_days?id=eq.{{ $json.id }}
  - Body: { "alert_start_sent": true, "status": "live" }

STEP 9e → Notify Manager of Live Match
  - POST /rest/v1/notifications
  - Body:
    ```json
    {
      "user_id": "{{ manager_id }}",
      "type": "match_alert",
      "title": "LIVE: {{ $json.title }}",
      "body": "Match is now live. {{ $json.users.name }} is on coverage.",
      "priority": "urgent",
      "match_day_id": "{{ $json.id }}",
      "channel": "in_app"
    }
    ```

STEP 10 → END (Merge branches back)
```

#### n8n Cron Workflow JSON Structure

```json
{
  "name": "Match Day Alert Engine",
  "nodes": [
    {
      "name": "Every 5 Minutes",
      "type": "n8n-nodes-base.cron",
      "parameters": {
        "triggerTimes": {
          "item": [{"mode": "everyX", "value": 5, "unit": "minutes"}]
        }
      },
      "position": [200, 300]
    },
    {
      "name": "Query Upcoming Matches",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "={{$env.SUPABASE_URL}}/rest/v1/match_days",
        "method": "GET",
        "queryParameters": {
          "parameters": [
            {"name": "status", "value": "eq.scheduled"},
            {"name": "select", "value": "*,users!match_days_assigned_executive_fkey(id,name,phone,slack_id)"}
          ]
        },
        "headers": {
          "parameters": [
            {"name": "apikey", "value": "={{$env.SUPABASE_ANON_KEY}}"},
            {"name": "Authorization", "value": "=Bearer {{$env.SUPABASE_SERVICE_ROLE_KEY}}"}
          ]
        }
      },
      "position": [400, 300]
    },
    {
      "name": "Has Matches",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "number": [{"value1": "={{$json.length}}", "operation": "larger", "value2": 0}]
        }
      },
      "position": [600, 300]
    },
    {
      "name": "Split Matches",
      "type": "n8n-nodes-base.splitInBatches",
      "parameters": {"batchSize": 1},
      "position": [800, 300]
    },
    {
      "name": "Calculate Time Diff",
      "type": "n8n-nodes-base.code",
      "parameters": {"jsCode": "/* See Step 5 code above */"},
      "position": [1000, 300]
    },
    {
      "name": "Alert Tier Router",
      "type": "n8n-nodes-base.switch",
      "parameters": {
        "dataType": "boolean",
        "rules": {
          "rules": [
            {"value1": "={{$json.should2hAlert}}", "output": 0},
            {"value1": "={{$json.should1hAlert}}", "output": 1},
            {"value1": "={{$json.shouldStartAlert}}", "output": 2}
          ]
        }
      },
      "position": [1200, 300]
    }
  ]
}
```

---

### 3c. Design Request Sync Flow

#### Overview
Triggered when a design request is submitted. Notifies design channel, generates a public tracking URL, and updates status.

#### Step-by-Step Workflow

```
WORKFLOW: design_request_sync
Trigger: Supabase Database Webhook (on INSERT to design_requests)
  OR: n8n webhook called from Retool on form submit

STEP 1 → Webhook Trigger
  - Listen for POST at /webhook/design-request-submitted
  - Payload: Full design_request row with tracking_token

STEP 2 → Fetch Designer Users (HTTP Request → Supabase)
  - GET /rest/v1/users?role=eq.design&select=id,name,slack_id,phone
  - Returns all design team members

STEP 3 → Generate Tracking URL (Set node)
  - trackingUrl = https://retool.yourdomain.com/apps/design-tracker/{{ $json.tracking_token }}
  - priorityEmoji: urgent=🔴, high=🟠, medium=🟡, low=🟢

STEP 4 → Format Slack Design Channel Message (Set node)
  ```
  🎨 NEW DESIGN REQUEST
  ━━━━━━━━━━━━━━━━━━━━
  📌 Title: {{title}}
  🖼️ Asset Type: {{asset_type}}
  {{priorityEmoji}} Priority: {{priority}}
  ⏰ Deadline: {{deadline}}
  👤 Requested by: {{requested_by_name}}
  
  📝 Brief: {{description}}
  📋 Copy: {{copy_text}}
  🔗 Pinterest Refs: {{pinterest_links[0].url}}
  
  🔑 Tracking: {{trackingUrl}}
  ━━━━━━━━━━━━━━━━━━━━
  ```

STEP 5 → Post to Design Slack Channel (Slack node)
  - channel: #design-requests (or dedicated design Slack channel ID)
  - message: [formatted message from Step 4]
  - attachments: Pinterest link previews if available

STEP 6 → Send WhatsApp to Each Designer (Loop over designers)
  - For each designer in Step 2 result:
    POST Twilio WhatsApp API
    To: whatsapp:+{{designer.phone}}
    Body: [condensed version of Step 4 message + tracking URL]

STEP 7 → Create In-App Notifications for Design Team (Loop)
  - For each designer:
    POST /rest/v1/notifications
    {
      "user_id": "{{designer.id}}",
      "type": "design_update",
      "title": "New Design Request: {{title}}",
      "body": "{{priority}} priority {{asset_type}} — deadline {{deadline}}",
      "priority": "{{priority === 'urgent' ? 'urgent' : 'high'}}",
      "channel": "in_app"
    }

STEP 8 → Update design_request status to 'in_review' (HTTP Request)
  - PATCH /rest/v1/design_requests?id=eq.{{id}}
  - Body: { "status": "in_review" }

STEP 9 → Notify Requester of Submission Confirmation (HTTP Request)
  - POST /rest/v1/notifications
  - {
      "user_id": "{{requested_by}}",
      "type": "design_update",
      "title": "Design Request Submitted",
      "body": "Your request '{{title}}' has been sent to the design team. Track: {{trackingUrl}}",
      "priority": "normal",
      "channel": "in_app"
    }

STEP 10 → END
```

#### Public Tracking Page Setup (Retool)

The Retool public app `/design/{tracking_token}` is a **no-auth** page that queries:

```sql
SELECT
  dr.title,
  dr.description,
  dr.asset_type,
  dr.priority,
  dr.status,
  dr.deadline,
  dr.copy_text,
  dr.pinterest_links,
  dr.created_at,
  dr.completed_at,
  u.name AS requested_by_name,
  s.title AS series_title
FROM design_requests dr
LEFT JOIN users u ON dr.requested_by = u.id
LEFT JOIN series s ON dr.series_id = s.id
WHERE dr.tracking_token = {{ urlParams.token }}::uuid;
```

The page displays a **read-only status timeline** with the current stage highlighted, reference links, and copy text — no login required for design team members outside the org.

---

## SECTION 4: UI/UX WIREFRAME SPECIFICATIONS

### 4.1 Manager Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SIDEBAR            │  TOP BAR                                          │
│  ─────────────────  │  ─────────────────────────────────────────────── │
│  🏠 Dashboard       │  📧 Inbox [3 unread]  🏏 Matches Today: 2        │
│  📋 All Tasks       │                            🔔 Notifications [5]  │
│  📅 Series          │  ─────────────────────────────────────────────── │
│  🏏 Match Days      │                                                   │
│  🎨 Design Queue   │  METRIC CARDS ROW                                 │
│  📊 Analytics       │  ┌───────────────┐ ┌───────────────┐ ┌────────┐  │
│  📝 Publishing Log  │  │ Today's Tasks │ │  Pending      │ │ Active │  │
│  ⚙️  Settings       │  │      12       │ │  Approvals    │ │ Series │  │
│                     │  │  ↑3 from yest │ │      4        │ │   6    │  │
│  ─────────────────  │  │  [View All]   │ │  [Review]     │ │ [View] │  │
│  👤 Manager Name    │  └───────────────┘ └───────────────┘ └────────┘  │
│  🔴 Live: 1 match   │                                                   │
│                     │  ASSIGNMENT PANEL                                 │
│                     │  ┌──────────────────────────────────────────────┐ │
│                     │  │ Quick Assign Series to Executive             │ │
│                     │  │  Series: [PSL 2026 ▼]  Executive: [Ali ▼]   │ │
│                     │  │  [Assign Now]  [+ Create New Series]         │ │
│                     │  │                                              │ │
│                     │  │  Active Assignments:                         │ │
│                     │  │  Series            Executive    Tasks  Status │ │
│                     │  │  PSL 2026          Ali Ahmed    8/12   🟢     │ │
│                     │  │  ICC Trophy        Sara Khan    3/7    🟡     │ │
│                     │  │  Super League      Bilal Raza   5/5    🔴     │ │
│                     │  └──────────────────────────────────────────────┘ │
│                     │                                                   │
│                     │  BOTTOM ROW: Charts + Design Bottlenecks         │
│                     │  ┌────────────────────┐ ┌──────────────────────┐ │
│                     │  │ Weekly Task Trend  │ │ Design Bottlenecks   │ │
│                     │  │  📊 Bar Chart      │ │  Request    Age  Pri │ │
│                     │  │  Mon-Sun           │ │  PSL Poster  3d  🔴  │ │
│                     │  │  Completed/Total   │ │  Story Set   1d  🟠  │ │
│                     │  │                   │ │  Carousel    5h  🟡  │ │
│                     │  └────────────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Interactions:**
- Clicking metric cards navigates to filtered task/series lists
- Assignment panel: dropdown filters by active series; executive dropdown shows workload count
- Design bottleneck table links to individual design request detail page
- Live match indicator in sidebar pulses red with match name on hover

---

### 4.2 Executive Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SIDEBAR            │  TOP BAR                                          │
│  ─────────────────  │  Hi Ali 👋  [Today: Thu 5 Jun]   🔔 Alerts [2]  │
│  🏠 My Dashboard   │                                                   │
│  📋 My Tasks        │  ── MATCH DAY ALERT BANNER (conditional) ───────  │
│  🎨 My Designs     │  │ 🏏 MATCH TODAY: PSL | Karachi vs Lahore       │  │
│  📅 My Series       │  │    🕐 19:00 PKT · National Stadium           │  │
│  📝 Publishing     │  │    [View Match Brief]  [Start Live Coverage]  │  │
│  ⚙️  Settings       │  ─────────────────────────────────────────────── │
│                     │                                                   │
│  ─────────────────  │  TASK KANBAN                                      │
│  👤 Ali Ahmed       │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ │
│  Executive          │  │ANNOUNCE  │ │PRE-MATCH │ │POST-MATCH│ │ LIVE │ │
│  🟢 Online          │  │          │ │          │ │          │ │      │ │
│                     │  │[Card]    │ │[Card]    │ │[Card]    │ │[Card]│ │
│                     │  │PSL Open  │ │Karachi   │ │Result    │ │Score │ │
│                     │  │Status:   │ │Pre-Match │ │Graphics  │ │Cards │ │
│                     │  │Draft     │ │Copy DONE │ │Status:   │ │LIVE  │ │
│                     │  │Due: 6pm  │ │Design:🟡 │ │In Prog.  │ │      │ │
│                     │  │          │ │          │ │          │ │      │ │
│                     │  │[+ New]   │ │[+ New]   │ │[+ New]   │ │[+New]│ │
│                     │  └──────────┘ └──────────┘ └──────────┘ └──────┘ │
│                     │                                                   │
│                     │  DESIGN PIPELINE STATUS                           │
│                     │  ┌────────────────────────────────────────────┐  │
│                     │  │ My Design Requests                          │  │
│                     │  │  Title          Status      ETA   Track    │  │
│                     │  │  PSL Opening    In Progress  2hrs  [Link]  │  │
│                     │  │  Score Template Submitted    -     [Link]  │  │
│                     │  │  Story Pack     Completed    ✅    [Link]  │  │
│                     │  │                                             │  │
│                     │  │  [+ Request New Design Asset]               │  │
│                     │  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Task Card Detail (expanded on click):**
```
┌────────────────────────────────────┐
│ 📋 PSL Opening Announcement        │
│ Type: Announcement | Series: PSL   │
│ Status: [Draft ▼] (editable)       │
│ Due: Today 6:00 PM                 │
│ ─────────────────────────────────  │
│ Content Copy: [editable text area] │
│ Pinterest Refs: [+ Add link]       │
│ Phase: [Drafting ▼]                │
│ ─────────────────────────────────  │
│ [Submit for Approval] [Design Req] │
└────────────────────────────────────┘
```

---

### 4.3 Head of Department Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SIDEBAR            │  TOP BAR                              [Export PDF]│
│  ─────────────────  │  Department Overview · June 2026                  │
│  🏠 Overview        │  ─────────────────────────────────────────────── │
│  👥 Team Leaderboard│                                                   │
│  📈 Analytics       │  KPI CARDS ROW                                    │
│  🏏 All Matches     │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐ │
│  📊 Reports         │  │ Total  │ │On-Time │ │Design  │ │Avg Task    │ │
│  ⚙️  Settings       │  │ Tasks  │ │ Rate   │ │Backlog │ │Completion  │ │
│                     │  │  156   │ │  78%   │ │   9    │ │  4.2 hrs   │ │
│                     │  │ ↑12%   │ │ ↓3%    │ │ ⚠️     │ │ ↑0.5hrs    │ │
│                     │  └────────┘ └────────┘ └────────┘ └────────────┘ │
│                     │                                                   │
│                     │  EXECUTIVE LEADERBOARD                            │
│                     │  ┌──────────────────────────────────────────────┐ │
│                     │  │ #  Executive    Tasks  On-Time  Design  Score │ │
│                     │  │ 1  Sara Khan    32      94%      8       ⭐⭐⭐ │ │
│                     │  │ 2  Ali Ahmed    28      89%      5       ⭐⭐⭐ │ │
│                     │  │ 3  Bilal Raza   24      75%      12      ⭐⭐  │ │
│                     │  │ 4  Fatima N.    22      82%      6       ⭐⭐  │ │
│                     │  │ 5  Usman T.     20      70%      3       ⭐⭐  │ │
│                     │  └──────────────────────────────────────────────┘ │
│                     │                                                   │
│                     │  CHARTS ROW                                       │
│                     │  ┌───────────────────┐ ┌──────────────────────┐  │
│                     │  │ MoM Growth Chart  │ │ Bottleneck Alerts    │  │
│                     │  │ 📈 Line Chart     │ │ ⚠️ Design: 9 pending │  │
│                     │  │ Tasks / Month     │ │ ⚠️ Approvals: 4 stale│  │
│                     │  │ Apr May Jun       │ │ ✅ Matches: On track │  │
│                     │  └───────────────────┘ └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 4.4 Design Team View (Public / Semi-Public)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HEADER                                                                 │
│  🎨 Design Request Queue — [Broadcaster] Social Media Team              │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  FILTER BAR                                                             │
│  Priority: [All ▼]  Status: [All ▼]  Asset Type: [All ▼]  [Search...]  │
│  Showing 9 requests · Sorted by: Priority ↓                            │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  CARD GRID (3 columns)                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │ 🔴 URGENT        │  │ 🟠 HIGH           │  │ 🟡 MEDIUM        │      │
│  │ PSL Opening      │  │ Score Card       │  │ Series Logo Pack │      │
│  │ Graphic          │  │ Template         │  │ Carousel         │      │
│  │ ─────────────── │  │ ─────────────── │  │ ─────────────── │      │
│  │ Status: In Prog  │  │ Status: Submitted│  │ Status: In Review│      │
│  │ ⏰ Due: Today 5pm│  │ ⏰ Due: Tomorrow  │  │ ⏰ Due: Jun 8    │      │
│  │ By: Ali Ahmed    │  │ By: Sara Khan    │  │ By: Bilal Raza   │      │
│  │ ─────────────── │  │ ─────────────── │  │ ─────────────── │      │
│  │ 📋 Copy:         │  │ 📋 Copy:         │  │ 📋 Copy:         │      │
│  │ "PSL 2026 kicks  │  │ "Karachi 186/4  │  │ "Season begins   │      │
│  │  off tonight..." │  │  Lahore need... │  │  with 6 teams..." │      │
│  │ ─────────────── │  │ ─────────────── │  │ ─────────────── │      │
│  │ 📌 Pinterest [2] │  │ 📌 Pinterest [1] │  │ 📌 Pinterest [3] │      │
│  │ [View Refs]      │  │ [View Refs]      │  │ [View Refs]      │      │
│  │ ─────────────── │  │ ─────────────── │  │ ─────────────── │      │
│  │ 🔑 #abc123de     │  │ 🔑 #def456fg     │  │ 🔑 #ghi789jk     │      │
│  │ [Copy Track URL] │  │ [Copy Track URL] │  │ [Copy Track URL] │      │
│  │ [Mark Complete]  │  │ [Claim Request]  │  │ [Claim Request]  │      │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘      │
│                                                                         │
│  FOOTER: Last updated: 2 minutes ago  [Refresh]                        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Card State Logic:**
- `submitted` → shows [Claim Request] button
- `in_review` / `in_progress` → shows assigned designer name
- `revision_requested` → highlighted with orange border, shows revision notes
- `completed` → grayed out, moved to bottom of grid

---

## SECTION 5: RETOOL DASHBOARD COMPONENT SPECS

### 5.1 Manager Dashboard Components

| Component | Type | SQL Query | Update Action |
|---|---|---|---|
| Today's Task Count | Stat | `SELECT COUNT(*) FROM tasks WHERE DATE(created_at) = CURRENT_DATE` | Link to task list |
| Pending Approvals | Stat | `SELECT COUNT(*) FROM tasks WHERE status = 'pending_approval'` | Filter task list |
| Active Series | Stat | `SELECT COUNT(*) FROM series WHERE status = 'active'` | Navigate to series |
| Assignment Panel | Form + Table | `SELECT s.*, u.name FROM series s LEFT JOIN users u ON s.assigned_to = u.id WHERE s.status = 'active'` | `UPDATE series SET assigned_to = {{execSelect.value}} WHERE id = {{seriesSelect.value}}` |
| Weekly Trend Chart | Chart (Bar) | `SELECT DATE(created_at) as day, COUNT(*) as total, COUNT(*) FILTER (WHERE status='published') as done FROM tasks WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY day ORDER BY day` | Read-only |
| Design Bottleneck | Table | `SELECT * FROM v_design_queue WHERE status != 'completed' ORDER BY priority DESC LIMIT 10` | Click row → design detail |
| Inbox Counter | Badge | `SELECT COUNT(*) FROM email_alerts WHERE action_taken = 'flagged' AND created_at > NOW() - INTERVAL '24 hours'` | Open email_alerts modal |
| Match Today | Badge | `SELECT COUNT(*) FROM match_days WHERE DATE(match_datetime) = CURRENT_DATE AND status IN ('scheduled','live')` | Match day list |

#### Assignment Panel SQL

```sql
-- Fetch executives with current workload
SELECT
  u.id,
  u.name,
  u.email,
  COUNT(t.id) FILTER (WHERE t.status NOT IN ('published', 'approved')) AS active_tasks
FROM users u
LEFT JOIN tasks t ON t.assigned_to = u.id
WHERE u.role = 'executive' AND u.is_active = true
GROUP BY u.id, u.name, u.email
ORDER BY active_tasks ASC;
```

---

### 5.2 Executive Dashboard Components

| Component | Type | SQL Query | Update Action |
|---|---|---|---|
| Match Day Banner | Container (conditional) | `SELECT * FROM v_upcoming_matches WHERE assigned_executive = {{current_user_id}} LIMIT 1` | Show/hide based on result |
| Task Kanban | Kanban | `SELECT * FROM v_active_tasks WHERE assigned_to = {{current_user_id}} ORDER BY due_date ASC` | `UPDATE tasks SET status = {{newStatus}} WHERE id = {{task.id}}` |
| Design Pipeline | Table | `SELECT * FROM v_design_queue WHERE requested_by = {{current_user_id}}` | Click → design detail modal |
| Create Design Request | Form Modal | Trigger: Button click | `INSERT INTO design_requests (title, description, asset_type, priority, copy_text, pinterest_links, requested_by, task_id, deadline) VALUES (...)` |
| Task Status Updater | Select (inline) | Inline on kanban card | `UPDATE tasks SET status = {{value}}, updated_at = NOW() WHERE id = {{task.id}}` |
| Publishing Phase | Select (inline) | Inline on task card | `UPDATE tasks SET publishing_status = {{value}} WHERE id = {{task.id}}` |

#### Kanban Board SQL

```sql
-- Executive's kanban tasks grouped by type
SELECT
  t.id,
  t.title,
  t.type,
  t.status,
  t.publishing_status,
  t.due_date,
  t.content_copy,
  t.pinterest_refs,
  s.title AS series_title,
  (
    SELECT COUNT(*) FROM design_requests dr
    WHERE dr.task_id = t.id AND dr.status != 'completed'
  ) AS pending_design_count
FROM tasks t
LEFT JOIN series s ON t.series_id = s.id
WHERE t.assigned_to = {{ current_user.id }}
  AND t.status NOT IN ('published')
ORDER BY
  CASE t.type
    WHEN 'live_coverage' THEN 1
    WHEN 'pre_match' THEN 2
    WHEN 'post_match' THEN 3
    WHEN 'announcement' THEN 4
    WHEN 'adhoc' THEN 5
  END,
  t.due_date ASC NULLS LAST;
```

---

### 5.3 Head of Department Components

| Component | Type | SQL Query | Update Action |
|---|---|---|---|
| Executive Leaderboard | Table | See below | Sort by column |
| KPI Cards | 4x Stat | Aggregates on analytics_snapshots | Read-only |
| MoM Growth Chart | Line Chart | Monthly task counts last 6 months | Date range picker |
| Bottleneck Alerts | List | Overdue tasks + stale approvals | Click → navigate |

#### Leaderboard SQL

```sql
SELECT
  u.id,
  u.name,
  u.avatar_url,
  COUNT(t.id) AS total_tasks,
  COUNT(t.id) FILTER (WHERE t.status = 'published') AS completed_tasks,
  ROUND(
    COUNT(t.id) FILTER (WHERE t.status = 'published' AND t.updated_at <= t.due_date)::numeric
    / NULLIF(COUNT(t.id) FILTER (WHERE t.due_date IS NOT NULL), 0) * 100, 1
  ) AS on_time_rate,
  COUNT(dr.id) AS design_requests_submitted
FROM users u
LEFT JOIN tasks t ON t.assigned_to = u.id
  AND t.created_at >= DATE_TRUNC('month', CURRENT_DATE)
LEFT JOIN design_requests dr ON dr.requested_by = u.id
  AND dr.created_at >= DATE_TRUNC('month', CURRENT_DATE)
WHERE u.role = 'executive' AND u.is_active = true
GROUP BY u.id, u.name, u.avatar_url
ORDER BY completed_tasks DESC, on_time_rate DESC;
```

---

### 5.4 Design Queue Components (Public Retool App)

| Component | Type | SQL Query | Update Action |
|---|---|---|---|
| Request Cards | Card List | `SELECT * FROM v_design_queue` (no auth filter) | Claim / Complete buttons |
| Priority Filter | Select | Client-side filter on card list | Filter: `priority = {{priorityFilter.value}}` |
| Status Filter | Select | Client-side filter | Filter: `status = {{statusFilter.value}}` |
| Claim Button | Button (on card) | — | `UPDATE design_requests SET assigned_designer = {{designer_id}}, status = 'in_progress' WHERE id = {{card.id}}` |
| Complete Button | Button (on card) | — | `UPDATE design_requests SET status = 'completed', completed_at = NOW() WHERE id = {{card.id}}` |
| Pinterest Refs Modal | Modal | `SELECT pinterest_links FROM design_requests WHERE id = {{selectedCard.id}}` | Open on "View Refs" click |
| Tracking URL Copy | Text + Button | `tracking_token` field | Copy `/design/{{token}}` to clipboard |

#### Public Page Query (no-auth token lookup)

```sql
SELECT
  dr.title,
  dr.description,
  dr.asset_type,
  dr.priority,
  dr.status,
  dr.deadline,
  dr.copy_text,
  dr.pinterest_links,
  dr.created_at,
  dr.completed_at,
  u.name AS requested_by_name,
  s.title AS series_title,
  CASE dr.status
    WHEN 'submitted'           THEN 1
    WHEN 'in_review'           THEN 2
    WHEN 'in_progress'         THEN 3
    WHEN 'revision_requested'  THEN 3
    WHEN 'completed'           THEN 4
  END AS stage_number
FROM design_requests dr
LEFT JOIN users u ON dr.requested_by = u.id
LEFT JOIN series s ON dr.series_id = s.id
WHERE dr.tracking_token = {{ urlParams.token }}::uuid;
```

---

## SECTION 6: DEPLOYMENT ARCHITECTURE

### 6.1 Architecture Diagram

```
                        ┌─────────────────────────────────┐
                        │       MICROSOFT OUTLOOK          │
                        │   (Content Team Mailbox)         │
                        └────────────┬────────────────────┘
                                     │ Graph API Webhook
                                     ▼
┌──────────────┐         ┌───────────────────────┐
│   RETOOL     │         │        n8n            │
│  (Cloud)     │◄────────│  (Railway / Render)   │
│              │ Supabase│                       │
│  - Manager   │  REST   │  Workflows:           │
│  - Executive │         │  · Email Parser       │
│  - HOD       │         │  · Match Alerts       │
│  - Design    │         │  · Design Sync        │
│    (Public)  │         │  · Publishing Sync    │
└──────┬───────┘         └───────────┬───────────┘
       │                             │
       │ Supabase JS Client          │ Supabase REST / Webhooks
       ▼                             ▼
┌─────────────────────────────────────────────────┐
│              SUPABASE                            │
│  ┌──────────────┐  ┌──────────┐  ┌───────────┐  │
│  │  PostgreSQL  │  │  Auth    │  │ Realtime  │  │
│  │  (DB + RLS)  │  │  (JWT)   │  │ (WebSock) │  │
│  └──────────────┘  └──────────┘  └───────────┘  │
└─────────────────────────────────────────────────┘
       │                             │
       │                             │ Twilio API
       ▼                             ▼
┌──────────────┐         ┌───────────────────────┐
│  SLACK API   │         │  TWILIO WHATSAPP       │
│  (DMs +      │         │  BUSINESS API          │
│   Channels)  │         │  (Match Alerts)        │
└──────────────┘         └───────────────────────┘
```

### 6.2 Supabase Configuration

**Project Setup:**
1. Create Supabase project at `app.supabase.com`
2. Run all SQL from Section 2 in the SQL Editor
3. Enable Row Level Security on all tables (included in schema)
4. Configure Auth providers: Email/Password + optional Google SSO
5. Enable Realtime for `notifications`, `tasks`, `design_requests` tables:
   ```sql
   ALTER PUBLICATION supabase_realtime ADD TABLE notifications;
   ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
   ALTER PUBLICATION supabase_realtime ADD TABLE design_requests;
   ALTER PUBLICATION supabase_realtime ADD TABLE match_days;
   ```

**Realtime Subscription in Retool (JavaScript):**
```javascript
const { createClient } = supabase;
const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

client
  .channel('notifications')
  .on('postgres_changes', {
    event: 'INSERT',
    schema: 'public',
    table: 'notifications',
    filter: `user_id=eq.${currentUserId}`
  }, (payload) => {
    // Trigger notification banner in Retool
    showNotificationBanner(payload.new);
  })
  .subscribe();
```

### 6.3 n8n Self-Hosted Configuration (Railway)

**Railway Deployment:**
```
1. Create new Railway project
2. Add n8n service: docker image n8nio/n8n:latest
3. Set environment variables (see Section 6.6)
4. Add PostgreSQL addon for n8n's own workflow metadata
5. Set custom domain: n8n.yourdomain.com
6. Enable HTTPS (Railway provides automatically)
```

**n8n Workflows to Deploy:**
| Workflow | Trigger | Frequency |
|---|---|---|
| `outlook_email_parser` | Graph API webhook | Event-driven |
| `match_day_alert_engine` | Cron | Every 5 minutes |
| `design_request_sync` | Webhook (from Retool) | Event-driven |
| `publishing_status_sync` | Cron | Every 30 minutes |
| `daily_analytics_snapshot` | Cron | Daily at 23:55 PKT |
| `graph_webhook_renew` | Cron | Every 3 days (Graph webhooks expire) |

**Graph API Webhook Renewal Workflow:**
```
Microsoft Graph webhooks expire after 4,320 minutes (3 days max).
Schedule renewal every 2.5 days:

PATCH https://graph.microsoft.com/v1.0/subscriptions/{{subscriptionId}}
Body: { "expirationDateTime": "{{new_expiry_ISO_string}}" }
```

### 6.4 Microsoft Graph API Webhook Setup

**Step 1: Azure App Registration**
```
1. Go to portal.azure.com → Azure Active Directory → App registrations
2. New registration: "SocialMediaCRM-Outlook"
3. Redirect URI: https://n8n.yourdomain.com/oauth/callback
4. API Permissions → Add:
   - Mail.Read (Delegated)
   - Mail.ReadWrite (Delegated)
   - User.Read (Delegated)
5. Generate Client Secret → copy value
```

**Step 2: Create Webhook Subscription**
```http
POST https://graph.microsoft.com/v1.0/subscriptions
Authorization: Bearer {{access_token}}
Content-Type: application/json

{
  "changeType": "created",
  "notificationUrl": "https://n8n.yourdomain.com/webhook/outlook-parser",
  "resource": "/me/mailFolders/Inbox/messages",
  "expirationDateTime": "{{ISO date 3 days from now}}",
  "clientState": "{{WEBHOOK_SECRET}}"
}
```

**Step 3: Handle Validation in n8n**
The first request will be a GET with `?validationToken=...`. n8n webhook node must respond with the token as plain text within 10 seconds (handled in workflow Step 2).

### 6.5 Twilio WhatsApp Business API

**Setup Steps:**
```
1. Twilio Console → Messaging → WhatsApp Senders
2. Create WhatsApp Business Profile with broadcaster branding
3. Submit for Meta approval (2-5 business days)
4. Configure Approved Message Templates (required for first contact):
   - Template: "match_2h_alert"
   - Template: "match_1h_alert"
   - Template: "match_start_alert"
   - Template: "design_request_notify"
```

**n8n Twilio Node Configuration:**
```json
{
  "accountSid": "{{TWILIO_ACCOUNT_SID}}",
  "authToken": "{{TWILIO_AUTH_TOKEN}}",
  "from": "whatsapp:+{{TWILIO_WHATSAPP_NUMBER}}",
  "to": "whatsapp:+{{recipient_phone}}",
  "body": "{{message_body}}"
}
```

### 6.6 Environment Variables

#### Supabase Project
```env
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGci...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...  # n8n only — never expose to frontend
SUPABASE_JWT_SECRET=your-jwt-secret
```

#### n8n Instance
```env
# n8n Core
N8N_HOST=0.0.0.0
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://n8n.yourdomain.com
N8N_ENCRYPTION_KEY=your-32-char-random-key

# Database (n8n internal)
DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=railway-postgres-host
DB_POSTGRESDB_PORT=5432
DB_POSTGRESDB_DATABASE=n8n
DB_POSTGRESDB_USER=n8n_user
DB_POSTGRESDB_PASSWORD=secure-password

# Supabase (used in HTTP nodes)
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...

# Microsoft Graph
MICROSOFT_CLIENT_ID=your-azure-app-client-id
MICROSOFT_CLIENT_SECRET=your-azure-app-secret
MICROSOFT_TENANT_ID=your-tenant-id
GRAPH_WEBHOOK_SECRET=random-32-char-secret

# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_NUMBER=14155238886

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_DESIGN_CHANNEL_ID=C0xxxxxxxxx

# App Config
DEFAULT_TIMEZONE=Asia/Karachi
MANAGER_USER_ID=uuid-of-manager-user
```

#### Retool
```env
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGci...
N8N_WEBHOOK_BASE=https://n8n.yourdomain.com/webhook
APP_DOMAIN=https://retool.yourdomain.com
```

---

## SECTION 7: IMPLEMENTATION ROADMAP

### Overview Timeline

```
WEEK 1 ──── WEEK 2 ──── WEEK 3 ──── WEEK 4 ──── WEEK 5 ──── WEEK 6
  │              │           │           │           │           │
Phase 1 ──────►│◄── Phase 2 ──►│◄─ Phase 3 ─►│◄─ Phase 4 ─►│◄─Phase 5►│
Core DB+Auth   Automations  Design+Pub  Analytics  Testing+Training
```

---

### Phase 1: Core Database + Auth + Basic Dashboards (Week 1–2)

**Week 1 — Infrastructure & Database**

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 1 | Create Supabase project, run full SQL schema | Backend | All 9 tables live |
| 1 | Configure RLS policies | Backend | Secure data access |
| 2 | Set up user accounts for all 6 team members | Admin | Auth working |
| 2 | Create Railway project, deploy n8n container | DevOps | n8n accessible |
| 3 | Configure Retool workspace, connect Supabase | Frontend | DB connected |
| 3 | Seed test data (series, tasks, match days) | Backend | Test data available |
| 4–5 | Build Manager Dashboard in Retool | Frontend | Manager can view tasks |

**Week 2 — Executive & Design Dashboards**

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 6–7 | Build Executive Dashboard (kanban + task cards) | Frontend | Executives operational |
| 8 | Implement task status updates (inline editing) | Frontend | Task management working |
| 9 | Build Design Team public view | Frontend | Public URL accessible |
| 10 | QA all dashboards, fix layout issues | QA | Stable v1 dashboards |

**Phase 1 Exit Criteria:**
- [ ] All users can log in with correct role-based views
- [ ] Manager can create series and assign to executives
- [ ] Executives can view and update their tasks
- [ ] Design team can view requests via public URL
- [ ] Basic task CRUD working end-to-end

---

### Phase 2: n8n Automations — Email Parser + Match Alerts (Week 3)

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 11 | Register Azure App, configure Graph API OAuth2 in n8n | Backend | OAuth2 credentials saved |
| 11 | Create Graph webhook subscription via n8n HTTP node | Backend | Webhook receiving events |
| 12 | Build Outlook Email Parser workflow (Steps 1–13) | Automation | Email → task creation |
| 12 | Test with real emails from content team mailbox | QA | Verified end-to-end |
| 13 | Build Match Day Alert Engine workflow | Automation | Alert cron operational |
| 13 | Configure Twilio WhatsApp templates (submit for approval) | DevOps | Templates submitted |
| 14 | Test all 3 alert tiers with mock match data | QA | Alert timing verified |
| 14 | Configure Slack bot, test DM delivery | Automation | Slack notifications live |
| 15 | Integration test: email receipt → task → notification | QA | Full flow verified |

**Phase 2 Exit Criteria:**
- [ ] Outlook emails auto-create adhoc tasks within 60 seconds
- [ ] Manager receives Slack DM on new content email
- [ ] 2-hour match alert fires correctly (tested with near-future match)
- [ ] 1-hour alert fires without duplicating 2-hour alert
- [ ] Match start alert updates status to 'live' in DB
- [ ] WhatsApp template approval received (or sandbox tested)

---

### Phase 3: Design Pipeline + Publishing Log (Week 4)

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 16 | Build "Create Design Request" form modal in Retool | Frontend | Executives can submit |
| 16 | Build n8n Design Request Sync workflow | Automation | Slack + WhatsApp on submit |
| 17 | Add Retool public tracking page with token routing | Frontend | `/design/{token}` live |
| 17 | Implement "Claim" and "Complete" actions on design view | Frontend | Designer can self-assign |
| 18 | Build Publishing Log entry form (per task) | Frontend | Publishing tracked |
| 18 | Build publishing log table view (manager view) | Frontend | Manager sees all platforms |
| 19 | Test full design request lifecycle | QA | Submit → complete flow |
| 20 | Build in-app notification bell with Supabase Realtime | Frontend | Live bell badge in Retool |

**Phase 3 Exit Criteria:**
- [ ] Design requests flow from executive to design team automatically
- [ ] Tracking URL accessible without login
- [ ] Designer can claim and complete requests from public view
- [ ] Publishing log entries created per task per platform
- [ ] In-app notification bell shows unread count in real-time

---

### Phase 4: Analytics + Head of Department Dashboard (Week 5)

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 21 | Build daily analytics snapshot n8n workflow | Automation | Nightly aggregations |
| 21 | Backfill analytics_snapshots for test period | Backend | Historical data |
| 22 | Build Head of Department dashboard | Frontend | HOD dashboard live |
| 22 | Implement executive leaderboard query | Frontend | Ranked table |
| 23 | Add MoM growth chart (Retool Chart component) | Frontend | Trend visualization |
| 23 | Build bottleneck alerts panel (overdue logic) | Frontend | Stale task warnings |
| 24 | Add PDF export for HOD reports | Frontend | Export button works |
| 25 | Performance testing: large dataset queries | QA | All queries < 500ms |

**Phase 4 Exit Criteria:**
- [ ] Daily snapshot cron runs and populates analytics table
- [ ] HOD can view executive leaderboard with correct ranking
- [ ] MoM chart reflects real task completion data
- [ ] Bottleneck alerts surface tasks overdue > 24 hours
- [ ] All dashboard pages load within 2 seconds

---

### Phase 5: Testing + Training + Go-Live (Week 6)

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 26 | Full end-to-end regression test (all workflows) | QA | Bug list |
| 26–27 | Fix priority bugs from regression | Dev | Stable release |
| 28 | User Acceptance Testing with Manager | QA + Manager | Sign-off |
| 28 | User Acceptance Testing with 2 Executives (pilot) | QA + Executives | Sign-off |
| 29 | Team training session (1h): Manager + Executives | Training | All users onboarded |
| 29 | Design team onboarding: public portal walkthrough | Training | Design team active |
| 30 | Monitor first live match day on platform | All | Live validation |
| 30 | Post-launch retrospective + backlog planning | PM | v1.1 roadmap |

**Phase 5 Exit Criteria:**
- [ ] All 6 team members can operate independently on the platform
- [ ] First live match day alerts fire correctly in production
- [ ] Zero critical bugs in production for 48 hours
- [ ] Monitoring + alerting configured for n8n failures
- [ ] Runbook documented for common issues

---

### Post-Launch Enhancements (v1.1 Backlog)

| Feature | Priority | Effort |
|---|---|---|
| Mobile-responsive Retool (or native mobile app) | High | 2 weeks |
| Sociality API integration for direct scheduling | High | 1 week |
| Instagram Insights API for post performance tracking | Medium | 1 week |
| AI-assisted caption generation (OpenAI API in n8n) | Medium | 3 days |
| Bulk task creation from match schedule import (CSV/Excel) | Medium | 2 days |
| Automated post-match social report PDF generation | Low | 1 week |
| Series-level content calendar Gantt view | Low | 1 week |

---

## Appendix A: Key URLs Reference

| Service | URL Pattern |
|---|---|
| Retool App | `https://retool.yourdomain.com/apps/crm` |
| Manager Dashboard | `https://retool.yourdomain.com/apps/crm/manager` |
| Executive Dashboard | `https://retool.yourdomain.com/apps/crm/executive` |
| Design Queue (Public) | `https://retool.yourdomain.com/apps/design-queue` |
| Design Tracker (Public) | `https://retool.yourdomain.com/apps/design-tracker?token={uuid}` |
| n8n Editor | `https://n8n.yourdomain.com` |
| Supabase Dashboard | `https://app.supabase.com/project/{project_id}` |
| Graph API Explorer | `https://developer.microsoft.com/en-us/graph/graph-explorer` |

---

## Appendix B: Cost Breakdown

| Service | Plan | Monthly Cost |
|---|---|---|
| Supabase | Pro ($25/mo) | $25 |
| n8n | Self-hosted on Railway Starter | $5–20 |
| Retool | Team (6 users × $10) | $60 |
| Twilio WhatsApp | Pay-per-message (~500 alerts/mo) | $5–15 |
| Railway (n8n hosting) | Starter plan | $5 |
| Microsoft 365 | Existing subscription | $0 (existing) |
| Slack | Existing workspace | $0 (existing) |
| **TOTAL** | | **~$100–125/mo** |

*Note: Excludes existing Microsoft 365 and Slack subscriptions. Significantly lower than any alternative stack.*

---

*Document prepared for Sports Broadcasting Social Media CRM v1.0*  
*Architecture validated against production requirements for a 6-person social media team*  
*Last updated: 2026-06-05*
