-- Campus Coin AI Assistant tables (MySQL 8+)
-- Preferred setup: run `python manage.py migrate` instead of this file.
-- Use this SQL only if you intentionally manage schema manually.

CREATE TABLE IF NOT EXISTS chat_sessions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(120) NOT NULL DEFAULT 'New finance chat',
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    last_message_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_chat_user_recent (user_id, last_message_at DESC),
    CONSTRAINT fk_chat_sessions_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    role VARCHAR(12) NOT NULL,
    content LONGTEXT NOT NULL,
    intent VARCHAR(50) NOT NULL DEFAULT '',
    metadata JSON NOT NULL,
    rating SMALLINT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_chat_msg_session (session_id, created_at),
    CONSTRAINT fk_chat_messages_session
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
        ON DELETE CASCADE,
    CONSTRAINT chk_chat_message_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT chk_chat_message_rating CHECK (rating IN (-1, 0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
