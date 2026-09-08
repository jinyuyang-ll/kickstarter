CREATE TABLE IF NOT EXISTS metadata_crawl_tasks (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_pid BIGINT NULL,
    project_url VARCHAR(1000) NOT NULL,
    crawl_status ENUM(
        'pending', 'processing', 'retry', 'filtered_year',
        'success', 'blocked', 'not_found'
    ) NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    last_status_code INT NULL,
    last_error VARCHAR(1000) NULL,
    last_attempt_at DATETIME NULL,
    next_retry_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id),
    UNIQUE KEY uk_metadata_task_url (project_url(500)),
    KEY idx_metadata_task_schedule (
        crawl_status, next_retry_at, attempt_count
    ),
    KEY idx_metadata_task_source_pid (source_pid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE metadata_crawl_tasks
    MODIFY COLUMN crawl_status ENUM(
        'pending', 'processing', 'retry', 'filtered_year',
        'success', 'blocked', 'not_found'
    ) NOT NULL DEFAULT 'pending';

CREATE TABLE IF NOT EXISTS project_metadata (
    project_id BIGINT NOT NULL,
    source_pid BIGINT NULL,
    project_link VARCHAR(1000) NOT NULL,
    title VARCHAR(1000) NULL,
    currency VARCHAR(10) NULL,
    goal_amount DECIMAL(24, 4) NULL,
    pledged_amount DECIMAL(24, 4) NULL,
    funding_start_date DATE NULL,
    funding_end_date DATE NULL,
    backers_count BIGINT NULL,
    project_status VARCHAR(50) NULL,
    creator_id VARCHAR(100) NULL,
    raw_json JSON NULL,
    first_crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id),
    KEY idx_project_metadata_year (funding_start_date),
    KEY idx_project_metadata_creator (creator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creator_metadata (
    creator_id VARCHAR(100) NOT NULL,
    creator_name VARCHAR(500) NULL,
    profile_url VARCHAR(1000) NULL,
    joined_date DATE NULL,
    created_project_count INT NULL,
    backed_project_count INT NULL,
    total_backers_across_projects BIGINT NULL,
    location VARCHAR(500) NULL,
    biography MEDIUMTEXT NULL,
    external_links JSON NULL,
    verified_identity TINYINT(1) NULL,
    raw_json JSON NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (creator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS collaborator_metadata (
    collaborator_id VARCHAR(100) NOT NULL,
    collaborator_name VARCHAR(500) NULL,
    profile_url VARCHAR(1000) NULL,
    joined_date DATE NULL,
    created_project_count INT NULL,
    backed_project_count INT NULL,
    total_backers_across_projects BIGINT NULL,
    location VARCHAR(500) NULL,
    biography MEDIUMTEXT NULL,
    external_links JSON NULL,
    is_service_provider TINYINT(1) NULL,
    service_category VARCHAR(200) NULL,
    classification_source VARCHAR(200) NULL,
    classification_confidence DECIMAL(5, 4) NULL,
    classification_version VARCHAR(50) NULL,
    raw_json JSON NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (collaborator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS project_collaborator (
    project_id BIGINT NOT NULL,
    collaborator_id VARCHAR(100) NOT NULL,
    collaborator_role VARCHAR(500) NULL,
    collaborator_link VARCHAR(1000) NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, collaborator_id),
    KEY idx_project_collaborator_person (collaborator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
