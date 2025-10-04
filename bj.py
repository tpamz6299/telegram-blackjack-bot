#!/usr/bin/env python3

import random
import logging
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Card deck
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']


class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def value(self):
        if self.rank in ['J', 'Q', 'K']:
            return 10
        elif self.rank == 'A':
            return 11
        else:
            return int(self.rank)


class Deck:
    def __init__(self):
        self.cards = [Card(suit, rank) for suit in SUITS for rank in RANKS]
        self.shuffle()
    
    def shuffle(self):
        random.shuffle(self.cards)
    
    def deal(self):
        if len(self.cards) < 10:  # Reshuffle if running low
            self.__init__()
        return self.cards.pop()


class MultiplayerBlackjackGame:
    def __init__(self, group_id, creator_id, creator_name):
        self.group_id = group_id
        self.players = {}  # {user_id: {'name': name, 'hand': [], 'status': 'waiting/playing/busted/stood', 'total_score': 0}}
        self.dealer_hand = []
        self.deck = Deck()
        self.game_state = 'waiting'  # waiting, in_progress, finished
        self.current_player_index = 0
        self.creator_id = creator_id
        self.message_id = None
        self.created_time = datetime.now()
        self.last_activity = datetime.now()
        
        # Add creator as first player
        self.add_player(creator_id, creator_name)
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
    
    def add_player(self, user_id, user_name):
        if user_id not in self.players and len(self.players) < 6:  # Max 6 players
            self.players[user_id] = {
                'name': user_name,
                'hand': [],
                'status': 'waiting',
                'game_score': 0,
                'total_score': 0  # Cumulative score across games
            }
            self.update_activity()
            return True
        return False
    
    def start_game(self):
        if len(self.players) < 1:
            return False
        
        self.game_state = 'in_progress'
        self.deck = Deck()
        self.dealer_hand = []
        
        # Deal initial cards to all players and dealer
        for player_id in self.players:
            self.players[player_id]['hand'] = [self.deck.deal(), self.deck.deal()]
            self.players[player_id]['status'] = 'playing'
            self.players[player_id]['game_score'] = 0
        
        self.dealer_hand = [self.deck.deal(), self.deck.deal()]
        self.current_player_index = 0
        self.update_activity()
        
        return True
    
    def calculate_hand_value(self, hand):
        value = 0
        aces = 0
        
        for card in hand:
            if card.rank == 'A':
                aces += 1
            value += card.value()
        
        # Adjust for aces
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        
        return value
    
    def get_current_player_id(self):
        player_ids = list(self.players.keys())
        if self.current_player_index < len(player_ids):
            return player_ids[self.current_player_index]
        return None
    
    def player_hit(self, user_id):
        if user_id != self.get_current_player_id():
            return "not_your_turn"
        
        player = self.players[user_id]
        player['hand'].append(self.deck.deal())
        player_value = self.calculate_hand_value(player['hand'])
        
        if player_value > 21:
            player['status'] = 'busted'
            self.update_activity()
            return "bust"
        
        self.update_activity()
        return "continue"
    
    def player_stand(self, user_id):
        if user_id != self.get_current_player_id():
            return "not_your_turn"
        
        self.players[user_id]['status'] = 'stood'
        self.update_activity()
        return "stood"
    
    def next_player(self):
        self.current_player_index += 1
        current_player_id = self.get_current_player_id()
        
        # Skip players who are done
        while (current_player_id and 
               self.players[current_player_id]['status'] in ['busted', 'stood']):
            self.current_player_index += 1
            current_player_id = self.get_current_player_id()
        
        # If no more players, dealer plays
        if not current_player_id:
            self.dealer_play()
            self.game_state = 'finished'
            self.calculate_results()
            self.update_activity()
            return "game_over"
        
        self.update_activity()
        return "next_player"
    
    def dealer_play(self):
        dealer_value = self.calculate_hand_value(self.dealer_hand)
        
        # Dealer must hit until 17 or higher
        while dealer_value < 17:
            self.dealer_hand.append(self.deck.deal())
            dealer_value = self.calculate_hand_value(self.dealer_hand)
    
    def calculate_results(self):
        dealer_value = self.calculate_hand_value(self.dealer_hand)
        
        for player_id, player in self.players.items():
            player_value = self.calculate_hand_value(player['hand'])
            
            if player['status'] == 'busted':
                player['result'] = 'bust'
                player['game_score'] = -1
            elif dealer_value > 21:
                player['result'] = 'dealer_bust'
                player['game_score'] = 1
            elif player_value > dealer_value:
                player['result'] = 'win'
                player['game_score'] = 1
            elif player_value < dealer_value:
                player['result'] = 'lose'
                player['game_score'] = -1
            else:
                player['result'] = 'push'
                player['game_score'] = 0
            
            # Update total score
            player['total_score'] += player['game_score']
    
    def get_game_display(self):
        text = "🎮 **Multiplayer Blackjack** 🎮\n\n"
        
        if self.game_state == 'waiting':
            text += "🕐 **Waiting for players...**\n"
            text += f"👥 Players joined ({len(self.players)}/6):\n"
            for player_id, player in self.players.items():
                text += f"• {player['name']}"
                if player['total_score'] != 0:
                    text += f" (Score: {player['total_score']})"
                text += "\n"
            text += f"\nClick ➕ Join to play!"
            
        elif self.game_state == 'in_progress':
            current_player_id = self.get_current_player_id()
            current_player_name = self.players[current_player_id]['name'] if current_player_id else "Dealer"
            
            text += f"🎯 **Current turn: {current_player_name}**\n\n"
            
            # Show dealer's hand (first card hidden)
            text += "💼 **Dealer:** "
            text += f"{self.dealer_hand[0]} ❓\n\n"
            
            # Show all players' hands and status
            for player_id, player in self.players.items():
                status_emoji = {
                    'waiting': '⏳',
                    'playing': '🎲',
                    'stood': '✋',
                    'busted': '💥'
                }.get(player['status'], '❓')
                
                text += f"{status_emoji} **{player['name']}:** "
                text += f"{' '.join(str(card) for card in player['hand'])} "
                text += f"({self.calculate_hand_value(player['hand'])})\n"
                
                if player['status'] == 'busted':
                    text += "   💥 BUSTED!\n"
                elif player['status'] == 'stood':
                    text += "   ✋ STOOD\n"
                text += "\n"
            
        elif self.game_state == 'finished':
            text += "🏁 **Game Finished!** 🏁\n\n"
            
            # Show dealer's full hand
            dealer_value = self.calculate_hand_value(self.dealer_hand)
            text += f"💼 **Dealer:** {' '.join(str(card) for card in self.dealer_hand)} "
            text += f"({dealer_value})"
            if dealer_value > 21:
                text += " 💥 BUSTED!"
            text += "\n\n"
            
            # Show results for each player
            for player_id, player in self.players.items():
                player_value = self.calculate_hand_value(player['hand'])
                result_emoji = {
                    'win': '🎉',
                    'lose': '😞',
                    'push': '🤝',
                    'bust': '💥',
                    'dealer_bust': '🎉'
                }.get(player['result'], '❓')
                
                text += f"{result_emoji} **{player['name']}:** "
                text += f"{' '.join(str(card) for card in player['hand'])} "
                text += f"({player_value}) - "
                
                if player['result'] == 'win':
                    text += "WIN! 🎉"
                elif player['result'] == 'lose':
                    text += "Lose"
                elif player['result'] == 'push':
                    text += "Push (Tie)"
                elif player['result'] == 'bust':
                    text += "Busted! 💥"
                elif player['result'] == 'dealer_bust':
                    text += "Dealer Busted! 🎉"
                
                # Show score
                if player['game_score'] > 0:
                    text += " +1"
                elif player['game_score'] < 0:
                    text += " -1"
                
                text += f" | Total: {player['total_score']}\n"
        
        return text
    
    def get_control_buttons(self):
        if self.game_state == 'waiting':
            keyboard = [
                [InlineKeyboardButton("➕ Join Game", callback_data="join")],
                [InlineKeyboardButton("🚀 Start Game", callback_data="start_game")],
                [InlineKeyboardButton("❌ Cancel Game", callback_data="cancel")]
            ]
        elif self.game_state == 'in_progress':
            current_player_id = self.get_current_player_id()
            if current_player_id:
                keyboard = [
                    [InlineKeyboardButton("🃏 Hit", callback_data="hit"),
                     InlineKeyboardButton("✋ Stand", callback_data="stand")],
                    [InlineKeyboardButton("📊 Game Status", callback_data="status")]
                ]
            else:
                keyboard = [[InlineKeyboardButton("📊 Show Results", callback_data="status")]]
        else:  # finished
            keyboard = [
                [InlineKeyboardButton("🔄 Play Again", callback_data="rematch"),
                 InlineKeyboardButton("❌ End Game", callback_data="cancel")],
                [InlineKeyboardButton("📈 Leaderboard", callback_data="leaderboard")]
            ]
        
        return InlineKeyboardMarkup(keyboard)
    
    def is_inactive(self, hours=2):
        """Check if game has been inactive for specified hours"""
        return datetime.now() - self.last_activity > timedelta(hours=hours)


# Store active games by group ID
active_games: Dict[int, MultiplayerBlackjackGame] = {}


async def cleanup_inactive_games():
    """Periodically clean up inactive games"""
    while True:
        try:
            current_time = datetime.now()
            inactive_games = []
            
            for chat_id, game in active_games.items():
                if game.is_inactive(hours=2):  # Remove games inactive for 2 hours
                    inactive_games.append(chat_id)
            
            for chat_id in inactive_games:
                del active_games[chat_id]
                logger.info(f"Cleaned up inactive game in chat {chat_id}")
            
            await asyncio.sleep(3600)  # Check every hour
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message."""
    help_text = """
🎮 **Multiplayer Blackjack Bot** 🎮

**Commands for Groups:**
/blackjack - Start a new multiplayer blackjack game
/rules - Show blackjack rules
/score - Show player scores
/cleanup - Clean up inactive games (admin)

**How to Play in Groups:**
1. Use `/blackjack` to create a game
2. Others click "Join Game"
3. Creator clicks "Start Game"
4. Take turns hitting or standing
5. Beat the dealer without going over 21!

Have fun! 🃏
    """
    await update.message.reply_text(help_text)


async def blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new multiplayer blackjack game."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Check if game already exists in this group
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


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all button callbacks."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    action = query.data
    
    logger.info(f"User {user.id} pressed {action} in chat {chat_id}")
    
    try:
        # Check if game exists
        if chat_id not in active_games:
            await query.edit_message_text("No active game in this group. Use /blackjack to start one!")
            return
        
        game = active_games[chat_id]
        game.update_activity()
        
        if action == "join":
            if game.add_player(user.id, user.first_name):
                await query.edit_message_text(
                    game.get_game_display(),
                    reply_markup=game.get_control_buttons(),
                    parse_mode='Markdown'
                )
            else:
                await query.answer("Cannot join game (full or already joined)", show_alert=True)
        
        elif action == "start_game":
            if user.id == game.creator_id and game.game_state == 'waiting':
                if len(game.players) >= 1:
                    game.start_game()
                    await query.edit_message_text(
                        game.get_game_display(),
                        reply_markup=game.get_control_buttons(),
                        parse_mode='Markdown'
                    )
                else:
                    await query.answer("Need at least 1 player to start", show_alert=True)
            else:
                await query.answer("Only the game creator can start the game", show_alert=True)
        
        elif action == "hit":
            result = game.player_hit(user.id)
            if result == "not_your_turn":
                await query.answer("Wait for your turn!", show_alert=True)
                return
            elif result == "bust":
                # Player busted, move to next
                next_result = game.next_player()
            else:
                # Player continues, don't advance turn yet
                pass
            
            await query.edit_message_text(
                game.get_game_display(),
                reply_markup=game.get_control_buttons(),
                parse_mode='Markdown'
            )
        
        elif action == "stand":
            result = game.player_stand(user.id)
            if result == "not_your_turn":
                await query.answer("Wait for your turn!", show_alert=True)
                return
            
            # Move to next player
            next_result = game.next_player()
            
            await query.edit_message_text(
                game.get_game_display(),
                reply_markup=game.get_control_buttons(),
                parse_mode='Markdown'
            )
        
        elif action == "status":
            await query.edit_message_text(
                game.get_game_display(),
                reply_markup=game.get_control_buttons(),
                parse_mode='Markdown'
            )
        
        elif action == "rematch":
            if user.id == game.creator_id and game.game_state == 'finished':
                # Start new game with same players
                if game.start_game():
                    await query.edit_message_text(
                        game.get_game_display(),
                        reply_markup=game.get_control_buttons(),
                        parse_mode='Markdown'
                    )
                else:
                    await query.answer("Error starting new game", show_alert=True)
            else:
                await query.answer("Only creator can start rematch after game ends", show_alert=True)
        
        elif action == "leaderboard":
            leaderboard_text = "📈 **Leaderboard** 📈\n\n"
            players_sorted = sorted(game.players.items(), key=lambda x: x[1]['total_score'], reverse=True)
            
            for i, (player_id, player) in enumerate(players_sorted):
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                leaderboard_text += f"{medal} {player['name']}: {player['total_score']} points\n"
            
            await query.answer(leaderboard_text, show_alert=True)
        
        elif action == "cancel":
            if user.id == game.creator_id:
                del active_games[chat_id]
                await query.edit_message_text("❌ Game cancelled by creator.")
            else:
                await query.answer("Only the game creator can cancel", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        try:
            await query.answer("Error processing action", show_alert=True)
        except:
            pass  # Already answered or message deleted


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Blackjack rules."""
    rules_text = """
🎯 **Multiplayer Blackjack Rules:**

**Goal:** Beat the dealer by having a hand value closer to 21 without going over.

**Card Values:**
- Number cards = face value (2-10)
- Face cards (J, Q, K) = 10
- Ace = 1 or 11 (whichever is better)

**Game Flow:**
1. Players join the game
2. Each player gets 2 cards face up
3. Dealer gets 1 card face up, 1 face down
4. Players take turns:
   - **Hit**: Take another card
   - **Stand**: Keep current hand
5. If you go over 21, you **BUST** and lose
6. After all players finish, dealer reveals hidden card
7. Dealer must hit until they have 17 or more
8. Compare hands with dealer

**Winning:**
- Beat the dealer's hand without busting
- If dealer busts, all remaining players win
- Tie = push (bet returned)

**Scoring:**
- Win: +1 point
- Loss: -1 point
- Push: 0 points

**Good luck!** 🍀
    """
    await update.message.reply_text(rules_text, parse_mode='Markdown')


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current game scores or overall leaderboard."""
    chat_id = update.effective_chat.id
    
    if chat_id in active_games:
        game = active_games[chat_id]
        await update.message.reply_text(
            game.get_game_display(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("No active game in this group. Use /blackjack to start one!")



    
    async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean up inactive games (admin function)."""
    user = update.effective_user
    
    # Simple admin check - replace with actual admin IDs
    # Add your Telegram user ID here (you can get it from @userinfobot)
    if user.id not in [7992334111, 987654321]:  # Replace with actual admin IDs
        await update.message.reply_text("Only admins can use this command.")
        return
    
    cleaned_count = 0
    inactive_games = []
    
    for chat_id, game in active_games.items():
        if game.is_inactive(hours=1):  # Clean games inactive for 1 hour
            inactive_games.append(chat_id)
    
    for chat_id in inactive_games:
        del active_games[chat_id]
        cleaned_count += 1
    
    await update.message.reply_text(f"🧹 Cleaned up {cleaned_count} inactive games.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        # Notify user about error
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred while processing your request. Please try again."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")


def main():
    """Start the bot."""
    # Get token from environment variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ ERROR: Please set TELEGRAM_BOT_TOKEN environment variable!")
        print("💡 Create a .env file with: TELEGRAM_BOT_TOKEN=your_bot_token_here")
        return
    
    print("🎮 Starting Multiplayer Blackjack Bot...")
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("blackjack", blackjack_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("score", score_command))
    application.add_handler(CommandHandler("cleanup", cleanup_command))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Start cleanup task
    application.job_queue.run_once(
        lambda context: asyncio.create_task(cleanup_inactive_games()),
        when=1
    )
    
    # Start the bot
    print("🤖 Multiplayer Blackjack Bot is running...")
    print("Press Ctrl+C to stop")
    application.run_polling()


if __name__ == '__main__':
    main()
