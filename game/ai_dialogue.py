"""AI dialogue system for tax man arguments using OpenAI API."""

import os
from typing import Optional

class AIDialogue:
    """Handles AI-generated dialogue for tax man arguments using OpenAI API."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5-nano") -> None:
        """
        Initialize AI dialogue system.
        
        Args:
            api_key: OpenAI API key. If None, will try to get from OPENAI_API_KEY env var.
                     Falls back to hardcoded key from user's curl command if env var not set.
            model: Model to use. Default is "gpt-4o-mini" (cheapest valid model).
                   Try "gpt-5-nano" if you have access to it.
        """
        # API calls disabled; always use fallback responses
        self.client = None
        self.model = model
        print("AI Dialogue: API disabled, using fallback responses only.")
    
    def generate_tax_argument(self, player_coins: int, day: int, player_argument: str = "") -> str:
        """
        Generate a tax man argument dialogue using OpenAI API.
        
        Args:
            player_coins: Number of coins the player has
            day: Current day number
            player_argument: The player's argument text (what they typed)
            
        Returns:
            AI-generated dialogue response from the tax man
        """
        # API disabled: always return fallback
        return self._get_fallback_response(player_argument)
    
    def _get_fallback_response(self, player_argument: str = "") -> str:
        """Get a fallback mafia-style response when API is unavailable."""
        import random
        
        responses = [
            "Listen here, pal. I don't care what you think. The tax man always gets his cut. Pay up or we'll have a problem.",
            "You think I haven't heard this before? Everyone tries to weasel out. Everyone still pays. You're no different.",
            "Nice try, wise guy. But I've been doing this for 20 years. Your excuses don't mean squat to me. Pay your taxes.",
            "I don't have time for this nonsense. The treasury needs its due, and you're going to pay it. End of story.",
            "You can argue all you want, but the law is the law. No exceptions. No negotiations. Just pay up.",
            "I've heard every excuse in the book. Yours isn't special. Pay your taxes or face the consequences.",
            "The boss wants his money, and I want my commission. Your arguments won't change that. Pay up, now.",
            "You think you're the first person to try this? I've seen it all. Just pay the tax and save us both time.",
        ]
        
        if player_argument:
            # Add some context-aware responses
            context_responses = [
                f"Whatever you said about '{player_argument[:30]}...' doesn't matter. Pay up!",
                f"I don't care about your '{player_argument[:30]}...' excuse. The tax man always wins.",
                f"Your argument about '{player_argument[:30]}...' is irrelevant. Pay your taxes!",
            ]
            responses.extend(context_responses)
        
        return random.choice(responses)

    def check_persuasion(self, ai_response: str | None) -> bool:
        """
        Lightweight hook for game logic to decide if we should attempt a persuasion roll.
        Current game code only needs a boolean; return True when we have any response text.
        """
        return bool(ai_response and ai_response.strip())

