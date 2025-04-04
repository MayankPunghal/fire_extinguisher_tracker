
## Setup and Installation (Local)

Follow these steps to run the application on your local machine for development or testing.

**Prerequisites:**

*   Python 3.9 or later installed.
*   `pip` (Python package installer).
*   Git installed.
*   A Supabase account and project set up (see [Database Setup](#database-setup-supabase--migrations)).

**Steps:**

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-folder-name>
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    # Create venv
    python -m venv venv
    # Activate venv
    # Windows (cmd/powershell):
    .\venv\Scripts\activate
    # macOS/Linux (bash/zsh):
    source venv/bin/activate
    ```
    *(You should see `(venv)` at the beginning of your terminal prompt)*

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Copy the `.env.example` file to a new file named `.env`:
        ```bash
        # Windows:
        copy .env.example .env
        # macOS/Linux:
        cp .env.example .env
        ```
    *   **Edit the `.env` file:**
        *   Replace placeholder values with your actual credentials.
        *   `SECRET_KEY`: Generate a strong secret key (e.g., run `python -c "import secrets; print(secrets.token_hex(24))"`).
        *   `DATABASE_URL`: Your Supabase **Pooler** connection string URI (ending in `:6543/postgres`). **Remember to replace `[YOUR-PASSWORD]`**.
        *   `SUPABASE_URL`: Your Supabase project URL (e.g., `https://xyz.supabase.co`).
        *   `SUPABASE_KEY`: Your Supabase project `service_role` key (recommended for backend) or `anon` key.
        *   `FLASK_APP`: Should be `api/index.py`.
    *   **Important:** Never commit your `.env` file to Git. The `.gitignore` file should prevent this.

5.  **Set up the Database:**
    *   Run the database migration commands (see [Database Setup](#database-setup-supabase--migrations) section below). You must run `flask db upgrade` against your Supabase database.

6.  **Create Initial Admin User (Optional but Recommended):**
    *   Make sure your venv is active and `FLASK_APP` is set (see step 4 under Database Setup).
    *   Run: `flask create-admin`

7.  **Run the Local Development Server:**
    ```bash
    flask run
    # OR
    python -m flask run
    ```
    The application should be accessible at `http://127.0.0.1:5000` (or the port indicated).

## Configuration (Environment Variables)

The application relies on environment variables for configuration, especially sensitive credentials.

*   **Local:** Configure using the `.env` file (loaded by `python-dotenv`).
*   **Vercel:** Configure under Project Settings -> Environment Variables.

**Required Variables:**

| Variable          | Description                                                                                             | Example                                                                          | Source                |
| :---------------- | :------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------- | :-------------------- |
| `SECRET_KEY`      | **Required.** Strong random string used for session signing and CSRF protection.                        | `your_generated_long_random_hex_string`                                          | Generate locally      |
| `DATABASE_URL`    | **Required.** Connection string URI for your Supabase **Pooler** (Session Mode, port 6543).             | `postgresql://postgres:[PASSWORD]@...supabase.co:6543/postgres`                  | Supabase Dashboard    |
| `SUPABASE_URL`    | **Required.** Base URL for your Supabase project API.                                                   | `https://your_project_ref.supabase.co`                                           | Supabase Dashboard    |
| `SUPABASE_KEY`    | **Required.** Your Supabase `service_role` (secret) or `anon` (public) key for interacting with storage. | `your_long_supabase_api_key`                                                     | Supabase Dashboard    |
| `FLASK_ENV`       | Set to `production` on Vercel (handled by `vercel.json`), `development` locally (optional via `.env`).  | `production`                                                                     | Set in Vercel / `.env` |
| `FLASK_APP`       | Path to the Flask app instance (needed for local CLI commands).                                         | `api/index.py`                                                                   | Set in `.env` / Shell |

## Database Setup (Supabase & Migrations)

This application uses PostgreSQL via Supabase and Flask-Migrate for schema management.

**1. Supabase Project:**

*   Create a Supabase project if you haven't already.
*   Note your Database Password securely.
*   Get your **Connection Pooler URI** (Session Mode, port `6543`) from Project Settings -> Database.
*   Enable Supabase Storage and create a **public bucket** named `qrcodes`.
*   Set up **Row Level Security (RLS) Policies** on the `storage.objects` table:
    *   An `INSERT` policy allowing your chosen `SUPABASE_KEY` role (`anon` or `service_role`) to upload to the `qrcodes` bucket (`WITH CHECK (bucket_id = 'qrcodes')`).
    *   A `SELECT` policy allowing the `anon` role to read from the `qrcodes` bucket (`USING (bucket_id = 'qrcodes')`).
*   Get your `SUPABASE_URL` and `SUPABASE_KEY` (`service_role` recommended, or `anon`) from Project Settings -> API.

**2. Running Migrations (Locally):**

*   Make sure your local `.env` file is configured correctly to point to your Supabase database.
*   Activate your virtual environment (`venv`).
*   Set the `FLASK_APP` environment variable for your terminal session:
    *   Windows (cmd): `set FLASK_APP=api/index.py`
    *   Windows (PowerShell): `$env:FLASK_APP = "api/index.py"`
    *   macOS/Linux: `export FLASK_APP=api/index.py`
*   **Initialize (Only Once Per Project):**
    ```bash
    flask db init
    ```
    *(Commit the generated `migrations` folder)*
*   **Generate New Migration (After Model Changes):**
    ```bash
    flask db migrate -m "Description of model changes"
    ```
    *(Commit the new script in `migrations/versions/`)*
*   **Apply Migrations to Database:**
    ```bash
    flask db upgrade
    ```
    *(Run this locally against Supabase to set up tables initially and after generating new migrations)*

## Deployment (Vercel)

1.  **Push to GitHub/GitLab/Bitbucket:** Ensure your latest code, including `vercel.json`, `requirements.txt`, and the `migrations` folder, is pushed to your Git repository.
2.  **Import Project on Vercel:** Connect your Git repository to Vercel and import the project. Vercel should detect the configuration from `vercel.json`.
3.  **Configure Vercel Environment Variables:**
    *   Go to your Vercel Project Settings -> Environment Variables.
    *   Add `SECRET_KEY`, `DATABASE_URL` (Supabase Pooler URI), `SUPABASE_URL`, and `SUPABASE_KEY`.
    *   Mark sensitive keys (SECRET_KEY, DATABASE_URL, service_role key) as "Secret".
    *   Ensure they apply to the "Production" environment.
4.  **Apply Database Migrations (Important):** Before deploying code that depends on new database schema changes, ensure you have applied the corresponding migrations to your **production Supabase database** by running `flask db upgrade` locally while your `.env` points to the production `DATABASE_URL`. (More advanced setups might integrate this into a CI/CD pipeline).
5.  **Deploy:** Trigger a deployment on Vercel (usually automatic on push to the main branch, or manually via the dashboard). Check the build and runtime logs if issues occur.

## Usage

1.  **Access the App:** Open the deployed Vercel URL.
2.  **Login:**
    *   **Admin:** Use the default credentials (`admin`/`admin@1234`) or credentials for other admin accounts created. Admins see the full navigation and features.
    *   **User:** Use credentials created by an Admin. Users are typically redirected straight to the Scan QR page.
3.  **Admin Tasks:**
    *   **Add Extinguisher:** Navigate to "Add Item", fill in details, and submit. A QR code will be generated and stored.
    *   **View/Print QR:** Navigate to Home, click "View" for an extinguisher. Right-click/long-press the QR code image to save or print it for sticking onto the physical extinguisher.
    *   **Manage Users:** Navigate to "Users" to add, edit, or delete user accounts and roles.
    *   **View Reports:** Navigate to "Daily Report", select a date, and view the check-in status. Export to Excel if needed.
4.  **User/Admin Scanning:**
    *   Navigate to "Scan QR" (or get redirected automatically if a User).
    *   Grant camera permissions if prompted.
    *   Point the camera at the physical QR code on an extinguisher.
    *   Upon successful scan of a valid code, the app will automatically register the check-in and redirect (usually to the extinguisher detail page).

## Future Enhancements

*   Add more extinguisher details (Type, Capacity, Expiry Date, Service Date).
*   Implement an "Overdue Items" report.
*   Allow checkers to report issues (low pressure, damage) during check-in.
*   Photo upload for locations or check-in issues.
*   Dashboard view with key statistics.
*   Search, filtering, and pagination for lists.
*   Email notifications for overdue items or reported issues.
*   Password reset functionality.

## License

This project is licensed under the MIT License - see the LICENSE file (if included) for details. *(Consider adding an actual LICENSE file with the MIT license text)*