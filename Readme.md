# HostelDesk

> AI-assisted hostel complaint and task desk.

HostelDesk turns a hostel complaint photo and a short description into a structured, trackable task.

A student uploads a photo and one-line note. AI analyzes the complaint and suggests a category, severity, and worker. The warden reviews and approves or edits the recommendation, and the assigned worker can view and complete the task.

## Problem

Hostel complaints are often reported through WhatsApp messages or verbal requests. This makes it difficult to know:

- What complaints are still open
- Which complaints are overdue
- Who is responsible for fixing an issue
- Which problems keep repeating in the same block

## Solution

HostelDesk provides a simple complaint workflow:

```text
Student
   ↓
Photo + Note
   ↓
AI Analysis
   ↓
Warden Review
   ↓
Worker Assignment
   ↓
Task Completion
   ↓
Student Status
```

The core principle is:

> **AI suggests; the Warden decides.**

The AI does not make decisions about students.

## Key Features

### Student

- Upload a complaint photo
- Add a short description
- Submit a complaint
- Track complaint status
- View own complaints

### Warden

- View complaint queue
- See AI-generated category and severity
- Review suggested worker
- Approve or edit AI recommendations
- View repeat-problem alerts
- View daily complaint digest

### Worker

- View assigned tasks
- See complaint details
- Mark a task in progress
- Mark a task completed
- Add a completion note

### AI

The AI analyzes the complaint photo and text and suggests:

- Category
- Severity
- Worker type

Supported complaint categories:

- Electrical
- Plumbing
- Cleaning
- Furniture

## Architecture

```text
                    HostelDesk Web App
                           │
              ┌────────────┼────────────┐
              │            │            │
           Student       Warden       Worker
              │            │            │
              └────────────┼────────────┘
                           │
                       Backend API
                           │
                ┌──────────┴──────────┐
                │                     │
             Database              AI Service
                                      │
                                 Gemini API
```

## Complaint Lifecycle

```text
SUBMITTED
    ↓
AI_ANALYZED
    ↓
WARDEN_REVIEW
    ↓
ASSIGNED
    ↓
IN_PROGRESS
    ↓
COMPLETED
```

## Tech Stack

- Frontend: React
- Backend: FastAPI
- Database: PostgreSQL
- AI: Gemini API / Gemma 4
- Version Control: Git + GitHub

## Project Structure

```text
HostelDesk/
│
├── frontend/
│   └── React application
│
├── backend/
│   └── FastAPI application
│
├── README.md
├── LICENSE
└── .gitignore
```

## Getting Started

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd HostelDesk
```

### 2. Start the backend

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it.

Windows:

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the server:

```bash
uvicorn main:app --reload
```

### 3. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

Create a `.env` file in the backend.

Example:

```env
GEMINI_API_KEY=your_api_key_here
DATABASE_URL=your_database_url_here
```

**Never commit API keys or real student data to GitHub.**

## Development Branches

We use separate branches for each major workstream:

```text
main
feature/student
feature/warden-ai
feature/backend-worker
```

### Branch ownership

| Branch | Owner | Responsibility |
|---|---|---|
| `feature/student` | Team Lead | Student UI and complaint flow |
| `feature/warden-ai` | Member 2 | AI integration and Warden dashboard |
| `feature/backend-worker` | Member 3 | Backend, database, Worker workflow and insights |

The `main` branch contains the integrated version of the project.

## MVP Scope

The MVP focuses on:

- Student complaint submission
- Photo + text AI analysis
- Warden review and approval
- Worker task assignment
- Task completion
- Student status tracking
- Repeat-problem alerts
- Daily warden digest

## Future Work

Possible future extensions include:

- Mobile application
- Notifications
- Hostel entry/exit management
- Mess management
- Attendance
- Fee management

## Demo Flow

The main demonstration follows one complaint:

```text
1. Student uploads a photo of a broken fan
2. Student adds a short description
3. AI identifies the issue as electrical
4. AI suggests high severity and an electrician
5. Warden reviews and approves the recommendation
6. Worker receives the assigned task
7. Worker marks the task completed
8. Student sees the updated status
9. Warden sees repeat-problem alerts and the daily digest
```

## Privacy and Security

This project is a hackathon MVP.

- Use fake/demo student data
- Keep API keys server-side
- Do not commit `.env` files
- Do not commit real student records
- Validate AI input and output
- Keep the Warden in the decision loop

## License

This project is released under the MIT License.
