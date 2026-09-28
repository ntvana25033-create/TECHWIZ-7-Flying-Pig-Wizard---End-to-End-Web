from django.core.management.base import BaseCommand, CommandError

from finance_assistant.services import assistant_engine


class Command(BaseCommand):
    help = "Check whether the configured Groq model can be reached successfully."

    def handle(self, *args, **options):
        agent = getattr(assistant_engine, "agent", None)
        if agent is None or not agent.enabled:
            raise CommandError("Groq AI is not enabled. Check GROQ_API_KEY/GROQ_MODEL in .env.")

        client = agent._get_client()
        try:
            response = client.chat.completions.create(
                model=agent.model,
                messages=[
                    {
                        "role": "user",
                        "content": "Reply with exactly: CAMPUS_COIN_AI_OK",
                    }
                ],
                temperature=0.1,
                max_completion_tokens=40,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            raise CommandError(
                f"Groq request failed ({exc.__class__.__name__}). Check the API key, internet connection, model and quota."
            ) from exc

        self.stdout.write(self.style.SUCCESS(f"Groq connection OK. Model: {agent.model}"))
        self.stdout.write(f"Model response: {text}")
