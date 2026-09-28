from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


# Curated, source-grounded product knowledge for the Campus Coin web app.
# The LLM searches this catalogue instead of inventing features or navigation.
SITE_KNOWLEDGE = [
    {
        "id": "overview",
        "title": "Campus Coin overview and student navigation",
        "keywords": "overview home navigation menu pages campus coin student portal web features",
        "content": (
            "Campus Coin is a student personal-finance web portal. The signed-in student header links to: "
            "Transactions, Add Transaction, Import CSV, Categories, Analytics, Notifications, and AI Assistant. "
            "The account menu contains Profile settings, Login sessions, Change password, and Sign out. "
            "The AI Assistant is also available as a widget on student pages outside the full Assistant page."
        ),
        "paths": [
            "/transactions/transactions/",
            "/transactions/transactions/new/",
            "/transactions/import/csv/",
            "/transactions/categories/",
            "/report/",
            "/notifications/",
            "/assistant/",
        ],
    },
    {
        "id": "transactions",
        "title": "Transactions: view, add, edit, and delete",
        "keywords": "transaction add create edit update delete income expense amount description date history list giao dich them sua xoa",
        "content": (
            "Students can view their transaction history and create income or expense records. A transaction stores type, "
            "category, amount, description, and date. The selected category must have the same type as the transaction. "
            "Existing transactions can be edited or deleted from their corresponding actions. Student transaction records "
            "are scoped to the signed-in user."
        ),
        "paths": [
            "/transactions/transactions/",
            "/transactions/transactions/new/",
            "/transactions/transactions/<id>/edit/",
            "/transactions/transactions/<id>/delete/",
        ],
    },
    {
        "id": "categories",
        "title": "Income and expense categories",
        "keywords": "category categories income expense danh muc type classifier shared categories",
        "content": (
            "The student Categories page lists the available income and expense categories. These categories are shared by "
            "the transaction form, CSV import, the transaction-category classifier, and reports. Students browse categories; "
            "category creation/editing/deletion is an administrator function in the admin portal."
        ),
        "paths": ["/transactions/categories/", "/transactions/manage/categories/"],
    },
    {
        "id": "csv_import",
        "title": "CSV transaction import workflow",
        "keywords": "csv import upload template classify ai review confirm file columns batch excel bulk giao dich nhap file",
        "content": (
            "CSV import is a review-first workflow: 1) upload a UTF-8 .csv file, 2) the classifier suggests categories from "
            "descriptions, 3) review/correct the rows, and 4) confirm the batch. Nothing is written to the final Transaction "
            "table until confirmation. Supported columns are type, category, amount, description, date. Category may be blank. "
            "Type must be income or expense. The current UI expects USD amounts such as 12.50 or $12.50, and recommends "
            "YYYY-MM-DD dates. CSV files must be 5 MB or smaller. A downloadable CSV template is provided. Confirmed final "
            "choices can be used as feedback for the category classifier."
        ),
        "paths": [
            "/transactions/import/csv/",
            "/transactions/import/csv/template/",
            "/transactions/import/csv/<batch_id>/preview/",
        ],
    },
    {
        "id": "transaction_category_ai",
        "title": "Transaction category AI/classifier",
        "keywords": "ai classifier category prediction training feedback tfidf smart category suggested confidence machine learning",
        "content": (
            "Campus Coin has a transaction-category classifier separate from the conversational LLM. It can suggest a category "
            "from transaction text and records confidence/feedback fields. The project stores AITrainingExample rows and can learn "
            "additional category examples from reviewed transaction/import choices. This classifier should not be confused with "
            "the Groq-powered conversational AI Assistant."
        ),
        "paths": ["/transactions/ajax/ai-predict/", "/transactions/import/csv/"],
    },
    {
        "id": "analytics",
        "title": "Analytics and financial reports",
        "keywords": "analytics report chart trend graph today week month 3 months 6 months email report income expense balance category",
        "content": (
            "Analytics summarizes the signed-in student's stored transactions. Available periods are Today, Last 7 days, "
            "This month, 3 months, and 6 months, with a reference date. The dashboard calculates total income, total expenses, "
            "balance, category breakdowns, transaction count, and chart data. For 3- and 6-month views the trend is grouped by "
            "month; shorter periods use daily buckets. The user can submit the report form to send a text financial report to "
            "their account email, including a link back to the interactive report."
        ),
        "paths": ["/report/"],
    },
    {
        "id": "notifications",
        "title": "Student notifications",
        "keywords": "notification alert warning unread read weekly monthly savings low balance email thong bao",
        "content": (
            "The Notification Center shows the student's own notifications, newest first, up to 30 per page. Notification types "
            "implemented in the data model are Weekly summary, Monthly summary, Savings goal warning, and Low balance warning. "
            "Severity can be Information, Warning, or Critical. A notification may include income, expense, balance, savings-goal "
            "figures, an action link, and email delivery state. Students can mark one notification or all notifications as read."
        ),
        "paths": ["/notifications/"],
    },
    {
        "id": "assistant",
        "title": "AI Assistant and chat history",
        "keywords": "assistant chatbot chat ai groq llm conversation history context new chat delete chat rating feedback tool calling",
        "content": (
            "The AI Assistant supports saved chat sessions for the signed-in student. Users can start a new chat, reopen recent "
            "sessions, delete a chat, and rate assistant messages helpful or not helpful. In AI mode it uses a pretrained LLM "
            "through the Groq OpenAI-compatible API. The LLM understands natural language and can call trusted local Campus Coin "
            "tools. Financial numbers come from Django/database calculations, not from model guesses. If the external AI call fails, "
            "a deterministic fallback keeps core finance questions available."
        ),
        "paths": ["/assistant/"],
    },
    {
        "id": "profile",
        "title": "Profile settings and financial preferences",
        "keywords": "profile name email academic year allowance savings goal avatar photo currency timezone settings ho so",
        "content": (
            "Profile settings let the user update email, full name, academic year, monthly allowance, monthly savings goal, profile "
            "picture, and time zone. The current form fixes currency to USD. Accepted profile images are JPG/JPEG, PNG, WEBP, "
            "or GIF up to 5 MB. A user can replace or remove the current avatar. Monthly allowance and monthly savings goal must "
            "be non-negative."
        ),
        "paths": ["/account/profile/"],
    },
    {
        "id": "security",
        "title": "Password and login-session security",
        "keywords": "password security sessions devices revoke logout login session change password bao mat mat khau phien dang nhap",
        "content": (
            "The account menu provides Change password and Login sessions. Login sessions record device/user-agent, IP when available, "
            "creation/expiry/last activity, and revocation state. A user can revoke their own active sessions. Signing out ends the "
            "current authenticated session. Password reset is available through the forgot-password flow."
        ),
        "paths": [
            "/account/change-password/",
            "/account/sessions/",
            "/account/logout/",
            "/account/forgot-password/",
        ],
    },
    {
        "id": "authentication",
        "title": "Registration, login, and password reset",
        "keywords": "register registration login logout forgot password reset account authentication sign in sign up dang ky dang nhap quen mat khau",
        "content": (
            "Campus Coin supports student registration, login by email/password, logout, forgot-password, and token-based password reset. "
            "The application uses a custom User model and email as the username field. Account status can be Pending verification, Active, "
            "Disabled, or Locked; only active, non-deleted accounts are considered active."
        ),
        "paths": [
            "/account/register/",
            "/account/login/",
            "/account/logout/",
            "/account/forgot-password/",
        ],
    },
    {
        "id": "roles",
        "title": "Student and administrator roles",
        "keywords": "roles student admin administrator permission authorization access phan quyen sinh vien quan tri",
        "content": (
            "The custom Role model defines STUDENT and ADMIN. Student-only views use StudentRequiredMixin and admin-only views use "
            "AdminRequiredMixin. Administrators have a separate admin-account portal. The conversational assistant page itself is a "
            "student view; admin capabilities are managed in the dedicated admin portal."
        ),
        "paths": ["/account/admin-account/"],
    },
    {
        "id": "admin_users",
        "title": "Administrator user management",
        "keywords": "admin users create edit delete disable enable lock status password reset student management administrator",
        "content": (
            "The administrator portal includes an admin dashboard plus user management. Admins can list users, create users, view user "
            "details, edit users, toggle account status, send a password-reset action, and delete users. Admins also have their own profile, "
            "change-password page, and login-session management."
        ),
        "paths": [
            "/account/admin-account/",
            "/account/admin-account/users/",
            "/account/admin-account/users/add/",
            "/account/admin-account/profile/",
            "/account/admin-account/sessions/",
        ],
    },
    {
        "id": "admin_finance",
        "title": "Administrator category, transaction, and notification management",
        "keywords": "admin category transaction notification management manage finance system notifications filter",
        "content": (
            "Administrator-only finance views include category list/create/edit/delete and a system-wide transaction list. The admin "
            "notification-management page lists system notifications and can filter by notification kind and read/unread status."
        ),
        "paths": [
            "/transactions/manage/categories/",
            "/transactions/manage/transactions/",
            "/notifications/manage/",
        ],
    },
    {
        "id": "data_scope",
        "title": "AI data scope and grounding",
        "keywords": "data access privacy bank momo zalopay wallet external account scope source truth ai data",
        "content": (
            "The Campus Coin assistant can use data stored inside Campus Coin for the signed-in user when a local tool provides it. "
            "It does not automatically connect to or read bank accounts, cards, MoMo, ZaloPay, or other external wallets. User-specific "
            "financial claims should be grounded in Campus Coin database/tool results. General financial-literacy explanations may be "
            "generated from the pretrained LLM without claiming they are the user's personal data."
        ),
        "paths": ["/assistant/"],
    },
    {
        "id": "ai_architecture",
        "title": "Conversational AI architecture",
        "keywords": "architecture llm groq api openai compatible tool calling nlp generative ai machine learning deep learning if else fallback",
        "content": (
            "The conversational assistant is LLM-first when Groq is configured. A pretrained Large Language Model handles natural-language "
            "understanding, follow-up context, tool selection, and generation of the final response. Local Django tools retrieve verified "
            "Campus Coin data and perform deterministic financial calculations. The old intent/rule engine remains only as a resilience "
            "fallback when AI is unavailable. This means the project integrates AI; it does not train the LLM from scratch."
        ),
        "paths": ["/assistant/"],
    },
    {
        "id": "classifier_vs_llm",
        "title": "Difference between classifier learning and LLM chat",
        "keywords": "training train learning classifier llm feedback self learn model ai training examples",
        "content": (
            "There are two distinct AI-related components. The transaction category classifier uses stored AITrainingExample records and "
            "can incorporate reviewed category feedback. The conversational assistant calls a pretrained external LLM and does not update "
            "that model's weights after each chat. Chat-message ratings are stored for feedback but do not by themselves retrain the LLM."
        ),
        "paths": ["/assistant/", "/transactions/import/csv/"],
    },
    {
        "id": "currency",
        "title": "Currency behavior",
        "keywords": "currency usd vnd dollar money unit exchange rate tien te",
        "content": (
            "The current Campus Coin profile form exposes only USD ($), transaction forms label amounts in USD, and CSV import examples "
            "also use USD. Although the profile model has a currency_code field, the current UI fixes it to USD. The assistant should not "
            "pretend that live FX conversion is built into the web app."
        ),
        "paths": ["/account/profile/", "/transactions/transactions/new/"],
    },
    {
        "id": "technology",
        "title": "Project technology stack",
        "keywords": "technology stack django python mysql sqlite channels redis sklearn openai groq css javascript backend frontend database",
        "content": (
            "The project is a Django 5.2 Python web application with a custom authentication model. It supports MySQL by default and SQLite "
            "through configuration. Django Channels is installed for realtime-capable notification infrastructure; Redis can be configured, "
            "otherwise an in-memory channel layer is used. The transaction classifier uses scikit-learn. The conversational assistant uses "
            "the OpenAI Python client against Groq's OpenAI-compatible API. Frontend pages use Django templates, CSS, and JavaScript."
        ),
        "paths": [],
    },
    {
        "id": "limitations",
        "title": "Important current limitations",
        "keywords": "limitations unsupported cannot feature not available limitations live bank investment tax legal currency",
        "content": (
            "Current product limits include: no live bank/card/e-wallet connection; no live foreign-exchange conversion in the app; the "
            "assistant should not invent missing Campus Coin records; AI availability depends on a valid Groq API key/network/quota; and the "
            "assistant is intended for Campus Coin usage, budgeting, and financial literacy rather than unrestricted general-purpose chat."
        ),
        "paths": ["/assistant/"],
    },
]


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _score(query: str, item: dict) -> float:
    q = _normalize(query)
    if not q:
        return 0.0
    haystack = _normalize(" ".join([item["title"], item["keywords"], item["content"]]))
    q_tokens = set(q.split())
    h_tokens = set(haystack.split())
    overlap = len(q_tokens & h_tokens) / max(len(q_tokens), 1)
    substring = 1.0 if q in haystack else 0.0
    title_ratio = SequenceMatcher(None, q, _normalize(item["title"])).ratio()
    keyword_ratio = SequenceMatcher(None, q, _normalize(item["keywords"])).ratio()
    return (overlap * 0.58) + (substring * 0.18) + (title_ratio * 0.14) + (keyword_ratio * 0.10)


def search_site_knowledge(query: str, limit: int = 5) -> list[dict]:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 8))

    ranked = sorted(
        ((_score(query, item), item) for item in SITE_KNOWLEDGE),
        key=lambda pair: pair[0],
        reverse=True,
    )
    # Always return a few best source-grounded chunks; LLM can say when none actually answer the question.
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "content": item["content"],
            "paths": item.get("paths", []),
            "relevance": round(score, 4),
        }
        for score, item in ranked[:limit]
    ]
