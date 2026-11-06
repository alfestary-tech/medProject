login_request ="""
    SELECT login
    FROM account
    WHERE acs_active = 1
"""

logout_request = """
    UPDATE account
    SET acs_active = 0
    WHERE acs_active = 1
"""

log_in_ = """
    SELECT password
    FROM account
    WHERE login = ?
"""

check_login_ = """
    UPDATE account
    SET acs_active = 1
    WHERE login = ?
"""

reg_in_ = """
    SELECT login
    FROM account
    WHERE login = ?
"""

check_password_ = """
    INSERT INTO account (login, password)
    VALUES (?, ?)
"""

file_add_ = """
    INSERT INTO files (fileName, filePath)
    VALUES (?, ?)
"""

сheck_file_ = """
    SELECT fileName
    FROM files
    WHERE filePath = ?
"""

action_add_ = """
    INSERT INTO actions (pers, file)
    VALUES (
        (SELECT id FROM account WHERE acs_active = 1),
        (SELECT id FROM files WHERE filePath = ?)
    )
"""

add_date_ = """
    UPDATE account
    SET last_date = ?
    WHERE acs_active = 1
"""

check_date_ = """
    SELECT last_date
    FROM account
    WHERE acs_active = 1
"""

