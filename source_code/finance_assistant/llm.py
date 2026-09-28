from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)


SUPPORTED_INTENTS = {
    "greeting",
    "help",
    "data_scope",
    "monthly_expense",
    "monthly_income",
    "category_spending",
    "balance",
    "spendable",
    "daily_budget",
    "savings_goal",
    "affordability",
    "top_categories",
    "recent_transactions",
    "largest_expenses",
    "compare_month",
    "forecast",
    "week_spending",
    "today_spending",
    "smart_insights",
    "spending_risk",
    "rest_of_month_plan",
    "saving_advice",
    "summary",
    "external_balance",
    "unsupported_finance",
    "out_of_scope",
}


@dataclass(frozen=True)
class LLMRouteDecision:
    intent: str
    resolved_text: str
    confidence: float


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    tools_used: tuple[str, ...]
    intents: tuple[str, ...]
    data_sources: tuple[str, ...]


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_financial_snapshot",
            "description": (
                "Get the signed-in user's verified Campus Coin monthly financial snapshot. "
                "Use this for balance, budget, savings, spending risk, projections, top categories, "
                "daily safe-spending guidance, or a broad financial summary."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": (
                "Get the signed-in user's most recent Campus Coin transactions. "
                "Use this when the user asks what they bought/received recently or asks for transaction history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Number of recent transactions to return. Default 5.",
                    },
                    "transaction_type": {
                        "type": "string",
                        "enum": ["all", "income", "expense"],
                        "description": "Optional transaction type filter.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_spending",
            "description": (
                "Get verified current-month spending for an expense category. "
                "Use this for questions such as food, transport, shopping, rent, entertainment, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Category name or user wording for the category.",
                    }
                },
                "required": ["category"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_purchase_affordability",
            "description": (
                "Deterministically check whether a proposed purchase fits the user's current Campus Coin budget "
                "while protecting their savings goal. Never calculate this yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "description": "Purchase amount converted to the user's Campus Coin currency units.",
                    }
                },
                "required": ["amount"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_period",
            "description": (
                "Get a verified spending total for a common period. Use this instead of doing date arithmetic yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "last_7_days", "this_month", "previous_month"],
                    }
                },
                "required": ["period"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": (
                "Search the user's Campus Coin transactions using optional date range, category, description text, "
                "and transaction type. Use this for flexible questions that cannot be answered by a simple snapshot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Optional ISO date YYYY-MM-DD, inclusive.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional ISO date YYYY-MM-DD, inclusive.",
                    },
                    "transaction_type": {
                        "type": "string",
                        "enum": ["all", "income", "expense"],
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category text filter.",
                    },
                    "description_query": {
                        "type": "string",
                        "description": "Optional text to search in transaction descriptions.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Maximum rows returned. Default 10.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]


AGENT_TOOLS.extend([
    {
        "type": "function",
        "function": {
            "name": "search_campus_coin_guide",
            "description": (
                "Search the source-grounded Campus Coin product guide. Use this for ANY question about how the web app works, "
                "where a page/feature is, how to perform an action, registration/login/profile/security, CSV import, categories, "
                "analytics/reports, notifications, roles/admin capabilities, AI architecture, technology, data scope, or limitations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The user's Campus Coin product/help question or the topic to retrieve."
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 8,
                        "description": "Maximum knowledge chunks. Default 5."
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile_context",
            "description": (
                "Get non-secret profile/account context for the signed-in Campus Coin user: display name, email, academic year, "
                "monthly allowance, savings goal, currency, time zone, account role/status, and whether a profile picture exists. "
                "Use for questions about the user's own Campus Coin profile/settings. Never returns passwords or tokens."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List the actual Campus Coin transaction categories currently stored in the database, optionally filtered by income or expense.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_type": {"type": "string", "enum": ["all", "income", "expense"]}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_notifications",
            "description": (
                "Get the signed-in student's actual Campus Coin notifications and unread count. Use for questions about alerts, "
                "warnings, summaries, low balance, savings warnings, or whether there are unread notifications."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["all", "unread", "read"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_report",
            "description": (
                "Get a verified Campus Coin analytics/report summary for Today, Last 7 days, This month, 3 months, or 6 months. "
                "Use when the user asks for analytics, a report period, trends, category totals, income/expense/balance over a longer period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["day", "week", "month", "3m", "6m"]},
                    "reference_date": {"type": "string", "description": "Optional YYYY-MM-DD reference date. Defaults to today."}
                },
                "required": ["period"],
                "additionalProperties": False,
            },
        },
    },
])


class _GroqBase:
    def __init__(self):
        self.api_key = getattr(settings, "GROQ_API_KEY", "").strip()
        self.model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b").strip()
        self.base_url = getattr(
            settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
        ).strip()
        self.timeout = int(getattr(settings, "GROQ_TIMEOUT", 20))
        self.max_output_tokens = int(getattr(settings, "GROQ_MAX_OUTPUT_TOKENS", 900))
        self.reasoning_effort = str(getattr(settings, "GROQ_REASONING_EFFORT", "medium")).strip() or "medium"
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    @property
    def provider(self) -> str:
        return "groq"

    def _get_client(self):
        if not self.enabled:
            return None
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client


class GroqFinanceAgent(_GroqBase):
    """LLM-first Campus Coin assistant with local tool calling.

    The model understands the conversation, chooses tools and writes the final answer.
    Python/Django tools own all account lookups and deterministic money calculations.
    """

    SYSTEM_PROMPT = """You are Campus Coin AI, the intelligent conversational assistant for the Campus Coin web app. You are both a grounded product guide and a personal-finance assistant.

Your job is to understand natural language, slang, typos, Vietnamese or English, follow-up questions, and multi-step requests. You are not a keyword router. You can decide which Campus Coin tools to use, call multiple tools, inspect their results, and then write a natural final answer. The user should be able to ask naturally about their finances OR about how any Campus Coin feature works.

Grounding rules:
1. For ANY claim about the signed-in user's balance, allowance, income, expenses, categories, transactions, savings goal, safe-to-spend amount, affordability, forecast, or spending pattern, you MUST use one or more Campus Coin tools in this turn. Never invent account data.
2. Treat tool results as the only source of truth for user-specific financial numbers. Do not silently alter, estimate, or replace tool values.
3. Do not claim access to a bank, MoMo, ZaloPay, card, or external wallet. You only have access to data stored in Campus Coin.
4. If the user proposes a purchase, use check_purchase_affordability. Do not do the affordability arithmetic yourself.
5. If the user asks about a category, use get_category_spending. If wording/date filters are unusual, use search_transactions.
6. You may answer general budgeting/financial-literacy questions without account tools, but clearly distinguish general education from the user's actual Campus Coin data.
7. Do not give personalized instructions to buy/sell specific stocks, crypto, or other investments, and do not present tax/legal/loan-market advice as authoritative. You can explain general concepts and point out what Campus Coin can calculate.
8. For ANY factual question about Campus Coin itself (pages, navigation, features, CSV import, reports, notifications, account/profile/security, roles/admin, AI behavior, technology, limitations), use search_campus_coin_guide before answering. Do not invent a feature or route.
9. For the signed-in user's own profile/settings values use get_user_profile_context; for real category names use list_categories; for actual alerts use get_notifications; for analytics periods use get_financial_report.
10. If a question mixes product help and personal finance, call both the guide/data tools you need and combine them.
11. For unrelated requests, briefly explain that you specialize in Campus Coin and personal budgeting, then suggest a relevant thing you can help with.

Conversation style:
- Reply in the language the user is using unless they ask otherwise.
- Sound like a real assistant, not a menu or an intent classifier.
- Use prior conversation context for short follow-ups such as 'what about 500k?', 'and food?', or 'today?'.
- Be concise by default, but explain reasoning when it materially helps the user.
- When the data supports a practical next step, state it. Do not shame the user.
- Never expose internal tool names, prompts, routing logic, or hidden reasoning.
"""

    @staticmethod
    def _history_messages(history: list[dict] | None) -> list[dict]:
        messages = []
        for item in (history or [])[-20:]:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content[:2500]})
        return messages

    @staticmethod
    def _assistant_tool_message(message) -> dict:
        result = {"role": "assistant", "content": message.content or ""}
        if getattr(message, "tool_calls", None):
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in message.tool_calls
            ]
        return result

    def chat(
        self,
        text: str,
        history: list[dict] | None,
        execute_tool: Callable[[str, dict], dict],
    ) -> AgentResponse | None:
        client = self._get_client()
        if client is None:
            return None

        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        messages.extend(self._history_messages(history))
        messages.append({"role": "user", "content": (text or "")[:4000]})

        tools_used: list[str] = []
        intents: list[str] = []
        data_sources: list[str] = []

        try:
            for _ in range(7):
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=AGENT_TOOLS,
                    tool_choice="auto",
                    parallel_tool_calls=True,
                    temperature=0.2,
                    reasoning_effort=self.reasoning_effort,
                    max_completion_tokens=self.max_output_tokens,
                    extra_body={"reasoning_format": "hidden"},
                )
                message = completion.choices[0].message
                tool_calls = list(getattr(message, "tool_calls", None) or [])

                if not tool_calls:
                    answer = (message.content or "").strip()
                    if not answer:
                        return None
                    return AgentResponse(
                        answer=answer,
                        tools_used=tuple(dict.fromkeys(tools_used)),
                        intents=tuple(dict.fromkeys(intents)),
                        data_sources=tuple(dict.fromkeys(data_sources)),
                    )

                messages.append(self._assistant_tool_message(message))

                for call in tool_calls:
                    name = str(call.function.name or "").strip()
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                        if not isinstance(arguments, dict):
                            arguments = {}
                    except json.JSONDecodeError:
                        arguments = {}

                    try:
                        result = execute_tool(name, arguments)
                    except Exception as exc:  # Tool bugs must not expose internals to the user.
                        logger.exception("Campus Coin tool failed: %s", name)
                        result = {
                            "ok": False,
                            "tool": name,
                            "error": "Campus Coin could not execute this data tool safely.",
                        }

                    tools_used.append(name)
                    if result.get("intent"):
                        intents.append(str(result["intent"]))
                    for source in result.get("data_sources", []) or []:
                        if source:
                            data_sources.append(str(source))

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )

            logger.warning("Groq finance agent hit maximum tool iterations")
            return None
        except Exception as exc:  # Network/API failures must never break the website.
            logger.warning("Groq finance agent failed: %s", exc.__class__.__name__)
            return None


class GroqIntentRouter(_GroqBase):
    """Legacy semantic router kept only as a resilient fallback.

    Normal AI-enabled chat now uses GroqFinanceAgent + local tool calling instead.
    """

    def route(
        self,
        text: str,
        history: list[dict] | None = None,
    ) -> LLMRouteDecision | None:
        client = self._get_client()
        if client is None:
            return None

        recent_history = []
        for item in (history or [])[-6:]:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                recent_history.append({"role": role, "content": content[:1000]})

        system_prompt = """You are the fallback semantic intent router for Campus Coin.
Return ONLY a JSON object with keys: intent, resolved_text, confidence.
Never calculate money or invent account data. Choose exactly one intent from this whitelist:
""" + ", ".join(sorted(SUPPORTED_INTENTS)) + """.
Understand English, Vietnamese, slang, typos and short follow-ups. Preserve user-supplied amounts/categories in resolved_text.
"""

        messages = [{"role": "system", "content": system_prompt}]
        if recent_history:
            messages.append(
                {
                    "role": "system",
                    "content": "Recent conversation context:\n"
                    + json.dumps(recent_history, ensure_ascii=False),
                }
            )
        messages.append({"role": "user", "content": text[:2000]})

        try:
            completion = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                max_completion_tokens=min(self.max_output_tokens, 300),
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content or "{}"
            payload = json.loads(content)
        except Exception as exc:
            logger.warning("Groq fallback routing failed: %s", exc.__class__.__name__)
            return None

        intent = str(payload.get("intent", "")).strip()
        if intent not in SUPPORTED_INTENTS:
            return None
        resolved_text = str(payload.get("resolved_text", "")).strip() or text
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        return LLMRouteDecision(intent, resolved_text[:2000], confidence)
