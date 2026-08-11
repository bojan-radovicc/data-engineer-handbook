-- Day 1 Homework — sample data.
-- Meets the requirement: >= 3 tickets, >= 2 messages per ticket,
-- >= 2 distinct statuses (here: open, in_progress, resolved).
-- Idempotent: only seeds when the tickets table is empty.

INSERT INTO support.tickets (title, status, priority, category, created_by)
SELECT * FROM (VALUES
    ('Cannot log into the dashboard', 'open',        'high',   'access',          'alice@example.com'),
    ('CSV export is very slow',       'in_progress', 'medium', 'performance',     'bob@example.com'),
    ('Please add a dark mode',        'resolved',    'low',    'feature-request', 'carol@example.com')
) AS v(title, status, priority, category, created_by)
WHERE NOT EXISTS (SELECT 1 FROM support.tickets);

-- Two messages per ticket, attached by matching on title so this works
-- regardless of the generated ticket_id values.
INSERT INTO support.ticket_messages (ticket_id, message_text, author)
SELECT t.ticket_id, m.message_text, m.author
FROM support.tickets t
JOIN (VALUES
    ('Cannot log into the dashboard', 'I get a 403 right after entering my password.', 'alice@example.com'),
    ('Cannot log into the dashboard', 'Thanks — can you confirm which browser you use?', 'support@example.com'),
    ('CSV export is very slow',       'Exporting 50k rows takes over two minutes.',      'bob@example.com'),
    ('CSV export is very slow',       'We are profiling the query now, update soon.',    'support@example.com'),
    ('Please add a dark mode',        'A dark theme would be easier on the eyes.',        'carol@example.com'),
    ('Please add a dark mode',        'Shipped in v2.1 — closing this out.',              'support@example.com')
) AS m(title, message_text, author) ON m.title = t.title
WHERE NOT EXISTS (SELECT 1 FROM support.ticket_messages);
