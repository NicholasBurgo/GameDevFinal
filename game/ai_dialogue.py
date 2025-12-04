"""AI dialogue system for tax man arguments using OpenAI API."""

import os
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


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
        self.client = None
        self.model = model
        
        if OpenAI is None:
            print("ERROR: OpenAI library not installed. Install with: pip install openai")
            return
        
        # Try to get API key from environment variable first, then from file
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        # Fallback to reading from api_key.txt file (gitignored)
        if not api_key:
            api_key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api_key.txt")
            try:
                if os.path.exists(api_key_path):
                    with open(api_key_path, "r") as f:
                        api_key = f.read().strip()
            except Exception as e:
                print(f"Warning: Could not read API key from file: {e}")
        
        try:
            self.client = OpenAI(api_key=api_key)
            print(f"AI Dialogue initialized with model: {model}")
        except Exception as e:
            print(f"ERROR: Could not initialize OpenAI client: {e}")
            print("Make sure your API key is valid and the openai library is installed.")
    
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
        if self.client is None:
            error_msg = "ERROR: OpenAI client not initialized. Check console for details."
            print(error_msg)
            return error_msg
        
        # Build user message with player's argument if provided
        if player_argument:
            user_content = f"The player has {player_coins} coins and it's day {day}. They're arguing: '{player_argument}'. Respond as the unhinged mafia-style tax collector, addressing their specific argument."
        else:
            user_content = f"The player has {player_coins} coins and it's day {day}. They're trying to argue about paying taxes. Respond as the unhinged mafia-style tax collector."
        
        messages = [
            {
                "role": "system",
                "content": "You are an unhinged mafia-style tax collector in a retro game. You're aggressive, threatening, and use mob-like language. Keep responses short (2-3 sentences max). Be menacing and unhinged. Use phrases like 'see what happens', 'make you an offer', 'protection money', etc."
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        # Try primary model first, then fallback models
        models_to_try = [self.model, "gpt-4o-mini", "gpt-3.5-turbo"]
        
        for model_name in models_to_try:
            try:
                print(f"Trying OpenAI API with model: {model_name}")
                if player_argument:
                    print(f"Player argument: {player_argument[:50]}..." if len(player_argument) > 50 else f"Player argument: {player_argument}")
                
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=150,  # Limit response length
                    temperature=0.8  # Creative but consistent
                )
                
                result = response.choices[0].message.content.strip()
                print(f"API call successful with {model_name}! Response: {result[:100]}...")
                return result
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                print(f"Model {model_name} failed: {error_type}: {error_msg}")
                
                # Check for specific error types
                error_lower = error_msg.lower()
                
                # Quota/credit errors - don't try other models, use fallback response
                if "quota" in error_lower or "insufficient_quota" in error_lower or "exceeded" in error_lower:
                    print("  -> QUOTA ERROR: Your OpenAI account has run out of credits")
                    print("  -> Go to https://platform.openai.com/account/billing to add credits")
                    print("  -> Or set a different API key in the OPENAI_API_KEY environment variable")
                    print("  -> Using fallback response instead")
                    # Return a fallback mafia-style response instead of error
                    return self._get_fallback_response(player_argument)
                
                # Authentication errors - don't try other models
                if "api" in error_lower and ("key" in error_lower or "auth" in error_lower or "invalid" in error_lower):
                    error_display = "API Key Error: Your API key is invalid or expired. Please check your API key."
                    print("  -> AUTH ERROR: Invalid or expired API key")
                    print("  -> Get a new key from https://platform.openai.com/api-keys")
                    return error_display
                
                # Rate limit errors - don't try other models
                if "rate" in error_lower and "limit" in error_lower and "quota" not in error_lower:
                    error_display = "Rate Limit: Too many requests. Please wait a moment and try again."
                    print("  -> RATE LIMIT: Too many API calls. Wait a moment.")
                    return error_display
                
                # Network errors - don't try other models
                if "network" in error_lower or "connection" in error_lower or "timeout" in error_lower:
                    error_display = "Network Error: Could not connect to OpenAI API. Check your internet connection."
                    print("  -> NETWORK ERROR: Connection issue")
                    return error_display
                
                # If it's not a model-specific error, don't try other models
                if "model" not in error_lower and "invalid" not in error_lower:
                    # Generic API error
                    error_display = f"API Error: {error_type}"
                    print(f"  -> Generic API error")
                    return error_display
                
                # If this was the last model to try, return the error
                if model_name == models_to_try[-1]:
                    error_display = f"All models failed. Last error: {error_type}"
                    print(f"  -> Tried models: {', '.join(models_to_try)}")
                    return error_display
                
                # Otherwise, try the next model
                continue
        
        # Should never reach here, but just in case
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

