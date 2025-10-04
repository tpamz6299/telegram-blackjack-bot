#!/usr/bin/env python3

import random
import logging
import asyncio
import os
import time
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging for Replit
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

print("🚀 Starting Blackjack Bot on Replit...")

# Your existing game classes go here (Card, Deck, MultiplayerBlackjackGame)
# [PASTE ALL YOUR GAME CLASSES - they should work as-is]

# Store active games
active_games: Dict[int, MultiplayerBlackjackGame] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message."""
    help_text = """
🎮 **Blackjack Bot** 🎮

**Commands:**
/blackjack - Start a game
/rules - Show rules  
/score - Show scores

**Game Modes:**
• **Solo** (1 player): Play vs dealer
• **Tournament** (2+ players): Knockout competition!

Click /blackjack to start a game!
    """
    await update.message.reply_text(help_text)

async def blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new multiplayer blackjack game."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id in active_games:
        game = active_games[chat_id]
        await update.message.reply_text(
            game.get_game_display(),
            reply_markup=game.get_control_buttons(),
            parse_mode='Markdown'
        )
        return
    
    # Create new game
    game = MultiplayerBlackjackGame(chat_id, user.id, user.first_name)
    active_games[chat_id] = game
    
    message = await update.message.reply_text(
        game.get_game_display(),
        reply_markup=game.get_control_buttons(),
        parse_mode='Markdown'
    )
    
    game.message_id = message.message_id

# [PASTE YOUR button_handler, rules_command, score_command functions here]

def main():
    """Start the bot."""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not found in environment variables!")
        print("💡 Make sure you set it in Replit Secrets (lock icon)")
        return
    
    print("✅ Bot token found!")
    print("🤖 Starting Telegram bot...")
    
    try:
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("blackjack", blackjack_command))
        application.add_handler(CommandHandler("rules", rules_command))
        application.add_handler(CommandHandler("score", score_command))
        application.add_handler(CommandHandler("help", start))
        application.add_handler(CallbackQueryHandler(button_handler))
        
        print("✅ Bot started successfully!")
        print("📱 Send /start to your bot in Telegram to test")
        
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()