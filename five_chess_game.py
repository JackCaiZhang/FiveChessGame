import pygame
import sys
import random
import json
import os
import socket
import threading
import pickle
import time
from collections import defaultdict

# Initialize pygame
pygame.init()

# Constants
BASE_WIDTH, BASE_HEIGHT = 800, 800  # Base window size
BOARD_SIZE = 15  # 15x15 grid
MIN_ZOOM = 0.5
MAX_ZOOM = 1.5
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BROWN = (210, 180, 140)  # Board color
RED = (255, 0, 0)  # Highlight color
GREEN = (0, 128, 0)  # Button color
GRAY = (128, 128, 128)  # Button color
LIGHT_GRAY = (200, 200, 200)  # Panel color

# Global variables
zoom_level = 1.0
WIDTH, HEIGHT = BASE_WIDTH, BASE_HEIGHT
GRID_SIZE = int((BASE_WIDTH * 0.8) // (BOARD_SIZE + 1))  # Base grid size without zoom
board_offset_x = int(BASE_WIDTH * 0.1)  # 10% margin on left
board_offset_y = int(BASE_HEIGHT * 0.1)  # 10% margin on top
side_panel_width = int(BASE_WIDTH * 0.2)  # 20% of width for side panel

# Create the screen
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption('Five Chess Game (Gomoku)')

# Button class for UI elements
class Button:
    def __init__(self, x, y, width, height, text, color):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.hover_color = (min(color[0] + 30, 255), min(color[1] + 30, 255), min(color[2] + 30, 255))
        self.is_hovered = False
    
    def draw(self):
        color = self.hover_color if self.is_hovered else self.color
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, BLACK, self.rect, 2)  # Border
        
        font = pygame.font.Font(None, 28)
        text_surface = font.render(self.text, True, BLACK)
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)
    
    def check_hover(self, pos):
        self.is_hovered = self.rect.collidepoint(pos)
        return self.is_hovered
    
    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)

class Game:
    def __init__(self):
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = 'BLACK'  # BLACK goes first
        self.game_over = False
        self.winner = None
        self.last_move = None
        self.vs_ai = True  # By default, play against AI
        self.ai_player = 'WHITE'  # AI plays as white
        self.difficulty = 'Medium'  # Default difficulty: Easy, Medium, Hard
        self.move_history = []  # Store move history for undo functionality
        self.game_start_time = pygame.time.get_ticks()  # For game timer
        self.player_times = {'BLACK': 0, 'WHITE': 0}  # Track player times
        self.last_move_time = pygame.time.get_ticks()  # For tracking turn time
        
        # Network multiplayer attributes
        self.multiplayer = False
        self.is_host = False
        self.network = None
        self.player_color = None  # In multiplayer, which color this client plays
    
    def place_piece(self, row, col):
        """Place a piece on the board at the specified position"""
        if self.game_over or row < 0 or row >= BOARD_SIZE or col < 0 or col >= BOARD_SIZE:
            return False
        
        if self.board[row][col] is not None:
            return False  # Cell already occupied
        
        # Record current time for player timing
        current_time = pygame.time.get_ticks()
        if self.last_move_time > 0:
            self.player_times[self.current_player] += (current_time - self.last_move_time)
        self.last_move_time = current_time
        
        # Store move in history before making it
        move_data = {
            'row': row,
            'col': col,
            'player': self.current_player,
            'board_state': [[cell for cell in row] for row in self.board],
            'current_player': self.current_player,
            'game_over': self.game_over,
            'winner': self.winner,
            'last_move': self.last_move
        }
        self.move_history.append(move_data)
        
        # Make the move
        self.board[row][col] = self.current_player
        self.last_move = (row, col)
        
        # Check for win condition
        if self.check_win(row, col):
            self.game_over = True
            self.winner = self.current_player
            return True
        
        # Check if board is full (draw)
        if all(self.board[r][c] is not None for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)):
            self.game_over = True
            return True
        
        # Switch player
        self.current_player = 'WHITE' if self.current_player == 'BLACK' else 'BLACK'
        
        # If it's AI's turn and the game is not over
        if self.vs_ai and self.current_player == self.ai_player and not self.game_over:
            self.ai_move()
        
        return True
        
    def undo_move(self):
        """Undo the last move"""
        if not self.move_history:
            return False  # No moves to undo
        
        # Remove the last move from history
        last_move = self.move_history.pop()
        
        # If AI made a move after the player, we need to undo both
        if self.vs_ai and len(self.move_history) > 0 and self.current_player != self.ai_player:
            # Remove AI's move too
            ai_move = self.move_history.pop()
        
        # If there are no more moves, reset the game state
        if not self.move_history:
            self.reset()
            return True
        
        # Otherwise, restore the previous game state
        prev_state = self.move_history[-1]
        self.board = [[cell for cell in row] for row in prev_state['board_state']]
        self.current_player = prev_state['current_player']
        self.game_over = prev_state['game_over']
        self.winner = prev_state['winner']
        self.last_move = prev_state['last_move']
        
        # Update the last move time to now
        self.last_move_time = pygame.time.get_ticks()
        
        return True
        
    def check_win(self, row, col):
        """Check if the current move results in a win"""
        player = self.board[row][col]
        
        # Check all 4 directions (horizontal, vertical, 2 diagonals)
        directions = [
            [(0, 1), (0, -1)],  # Horizontal
            [(1, 0), (-1, 0)],  # Vertical
            [(1, 1), (-1, -1)],  # Diagonal /
            [(1, -1), (-1, 1)]   # Diagonal \
        ]
        
        for dir_pair in directions:
            count = 1  # Count the piece just placed
            
            # Check in both directions
            for dx, dy in dir_pair:
                for i in range(1, 5):  # Need 5 in a row to win
                    r, c = row + dx * i, col + dy * i
                    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
                        count += 1
                    else:
                        break
            
            if count >= 5:
                return True
        
        return False
        
    def check_opponent_threat(self, row, col, opponent):
        """Check if placing a piece at this position would block a potential threat from opponent"""
        # Temporarily place our piece here
        self.board[row][col] = self.current_player
        threat_score = 0
        
        # Check all 4 directions (horizontal, vertical, 2 diagonals)
        directions = [
            [(0, 1), (0, -1)],  # Horizontal
            [(1, 0), (-1, 0)],  # Vertical
            [(1, 1), (-1, -1)],  # Diagonal /
            [(1, -1), (-1, 1)]   # Diagonal \
        ]
        
        # Early termination if we find a very high threat
        max_threat_found = False
        
        for dir_pair in directions:
            if max_threat_found:
                break
                
            # Check for opponent's potential threats in this direction
            for dx, dy in dir_pair:
                # Look for opponent's pieces in this direction
                opponent_count = 0
                open_ends = 0
                
                # Check up to 4 spaces in this direction
                for i in range(1, 5):
                    r, c = row + dx * i, col + dy * i
                    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                        if self.board[r][c] == opponent:
                            opponent_count += 1
                        elif self.board[r][c] is None:
                            open_ends += 1
                            break
                        else:
                            break
                    else:
                        break
                
                # Check the opposite direction for open ends and opponent pieces
                for i in range(1, 5):
                    r, c = row - dx * i, col - dy * i
                    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                        if self.board[r][c] == opponent:
                            opponent_count += 1
                        elif self.board[r][c] is None:
                            open_ends += 1
                            break
                        else:
                            break
                    else:
                        break
                
                # Score the threat
                if opponent_count >= 4 and open_ends >= 1:
                    # Critical threat: opponent has 4 in a row with an open end
                    threat_score = max(threat_score, 100)
                    max_threat_found = True  # Early termination
                    break
                elif opponent_count == 3 and open_ends >= 2:
                    # Serious threat: opponent has 3 in a row with two open ends
                    threat_score = max(threat_score, 80)
                elif opponent_count == 3 and open_ends == 1:
                    # Moderate threat: opponent has 3 in a row with one open end
                    threat_score = max(threat_score, 50)
                elif opponent_count == 2 and open_ends >= 2:
                    # Minor threat: opponent has 2 in a row with two open ends
                    threat_score = max(threat_score, 30)
        
        # Undo our temporary move
        self.board[row][col] = None
        
        return threat_score
    
    def reset(self):
        """Reset the game"""
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = 'BLACK'
        self.game_over = False
        self.winner = None
        self.last_move = None
        self.move_history = []
        
        # Reset game timer
        self.game_start_time = pygame.time.get_ticks()
        self.player_times = {'BLACK': 0, 'WHITE': 0}
        self.last_move_time = pygame.time.get_ticks()
        
        # If AI goes first (as BLACK), make a move
        if self.vs_ai and self.ai_player == 'BLACK':
            self.ai_move()
            
    def ai_move(self):
        """Make a move for the AI player based on current difficulty"""
        # Get all valid moves (empty cells)
        valid_moves = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if self.board[row][col] is None:
                    valid_moves.append((row, col))
        
        if not valid_moves:
            return  # No valid moves
        
        # Evaluate each move
        best_move = None
        best_score = -float('inf')
        
        # Set randomness factor based on difficulty
        if self.difficulty == 'Easy':
            randomness = 20  # High randomness for easy mode
            depth = 0  # No look-ahead for faster response
        elif self.difficulty == 'Medium':
            randomness = 5   # Medium randomness
            depth = 1  # Less look-ahead for better responsiveness
        else:  # Hard
            randomness = 1   # Low randomness for hard mode
            depth = 1  # Reduced look-ahead depth for better responsiveness while maintaining intelligence
        
        # Optimize: First check if there's a winning move or a move to block opponent's win or threat
        opponent = 'WHITE' if self.current_player == 'BLACK' else 'BLACK'
        
        # First priority: Check for immediate winning move
        for row, col in valid_moves:
            self.board[row][col] = self.current_player
            if self.check_win(row, col):
                self.board[row][col] = None  # Undo the move
                self.place_piece(row, col)   # Make the winning move
                return
            self.board[row][col] = None  # Undo the move
        
        # Second priority: Block opponent's immediate winning move
        for row, col in valid_moves:
            self.board[row][col] = opponent
            if self.check_win(row, col):
                self.board[row][col] = None  # Undo the move
                self.place_piece(row, col)   # Block opponent's winning move
                return
            self.board[row][col] = None  # Undo the move
            
        # Third priority: Check for opponent's potential threats (3 or 4 in a row with open ends)
        threat_moves = []
        for row, col in valid_moves:
            threat_score = self.check_opponent_threat(row, col, opponent)
            if threat_score > 0:
                threat_moves.append((row, col, threat_score))
        
        # If we found threatening moves, block the most serious one
        if threat_moves:
            # Sort by threat score (highest first)
            threat_moves.sort(key=lambda x: x[2], reverse=True)
            self.place_piece(threat_moves[0][0], threat_moves[0][1])  # Block the biggest threat
            return
        
        # If no immediate winning or blocking move, evaluate positions
        # Limit the number of positions to evaluate for better responsiveness
        max_positions = 20 if self.difficulty == 'Hard' else 15
        
        # Count the number of moves made so far
        moves_made = sum(1 for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if self.board[r][c] is not None)
        
        # For the first few moves, prioritize responding near the player's pieces
        if moves_made <= 4:
            # Find player's pieces and prioritize moves near them
            player_pieces = []
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if self.board[r][c] == opponent:
                        player_pieces.append((r, c))
            
            # Sort valid moves by proximity to player's pieces
            if player_pieces:
                valid_moves.sort(key=lambda pos: min(abs(pos[0] - r) + abs(pos[1] - c) for r, c in player_pieces))
                # Take more positions to evaluate in early game for better response
                valid_moves = valid_moves[:max_positions]
            else:
                # If no player pieces yet (first move), prioritize center
                center = BOARD_SIZE // 2
                valid_moves.sort(key=lambda pos: abs(pos[0] - center) + abs(pos[1] - center))
                valid_moves = valid_moves[:max_positions]
        else:
            # Later in the game, balance between center control and responding to player
            center = BOARD_SIZE // 2
            valid_moves.sort(key=lambda pos: abs(pos[0] - center) + abs(pos[1] - center))
            valid_moves = valid_moves[:max_positions]
        
        # Set a time limit for move evaluation to prevent unresponsiveness
        start_time = time.time()
        time_limit = 0.5  # Maximum time in seconds for move evaluation
        
        for row, col in valid_moves:
            # Check if we've exceeded the time limit
            if time.time() - start_time > time_limit:
                break
                
            # Try this move
            score = self.evaluate_move(row, col, depth)
            
            # Add randomness to make AI less predictable (more for easy, less for hard)
            score += random.uniform(0, randomness)
            
            if score > best_score:
                best_score = score
                best_move = (row, col)
        
        # Make the best move
        if best_move:
            self.place_piece(best_move[0], best_move[1])
        # If we somehow don't have a best move (e.g., time limit exceeded before evaluation),
        # just pick the first valid move
    
    def evaluate_move(self, row, col, depth):
        """Evaluate a potential move at the given position"""
        # Base score for this position
        score = 0
        
        # Try placing the piece
        self.board[row][col] = self.current_player
        
        # Check if this move would win
        if self.check_win(row, col):
            score = 1000  # Very high score for winning move
        else:
            # Evaluate position based on threats
            score = self.evaluate_position(row, col)
            
            # Look ahead if depth > 0
            if depth > 0:
                # Switch player temporarily
                self.current_player = 'WHITE' if self.current_player == 'BLACK' else 'BLACK'
                
                # Find opponent's best response
                opponent_best_score = -float('inf')
                
                # Limit the number of responses to evaluate for better performance
                response_moves = []
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        if self.board[r][c] is None:
                            response_moves.append((r, c))
                
                # Prioritize center and positions near existing pieces
                center = BOARD_SIZE // 2
                response_moves.sort(key=lambda pos: abs(pos[0] - center) + abs(pos[1] - center))
                response_moves = response_moves[:15]  # Limit to 15 positions for better performance
                
                # Check all valid responses
                for r, c in response_moves:
                    # Recursively evaluate this response
                    response_score = self.evaluate_move(r, c, depth - 1)
                    opponent_best_score = max(opponent_best_score, response_score)
                    
                    # Early termination if we found a very good move for opponent
                    if opponent_best_score > 500:
                        break
                
                # Subtract opponent's best score (minimax principle)
                if opponent_best_score != -float('inf'):
                    score -= opponent_best_score
                
                # Switch back to original player
                self.current_player = 'WHITE' if self.current_player == 'BLACK' else 'BLACK'
        
        # Undo the move
        self.board[row][col] = None
        
        return score
    
    def evaluate_position(self, row, col):
        """Evaluate the strength of a position based on threats and proximity to existing pieces"""
        player = self.current_player
        score = 0
        
        # Check all 4 directions (horizontal, vertical, 2 diagonals)
        directions = [
            [(0, 1), (0, -1)],  # Horizontal
            [(1, 0), (-1, 0)],  # Vertical
            [(1, 1), (-1, -1)],  # Diagonal /
            [(1, -1), (-1, 1)]   # Diagonal \
        ]
        
        for dir_pair in directions:
            # Count consecutive pieces and open ends
            consecutive = 1  # The piece we just placed
            open_ends = 0
            
            # Check both directions
            for dx, dy in dir_pair:
                # Count consecutive pieces in this direction
                for i in range(1, 5):
                    r, c = row + dx * i, col + dy * i
                    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                        if self.board[r][c] == player:
                            consecutive += 1
                        elif self.board[r][c] is None:
                            open_ends += 1
                            break
                        else:
                            break
                    else:
                        break
            
            # Score based on consecutive pieces and open ends
            if consecutive >= 5:
                score += 100  # Win
            elif consecutive == 4:
                if open_ends >= 1:
                    score += 50  # Four in a row with an open end
                else:
                    score += 25  # Four in a row with no open ends still valuable
            elif consecutive == 3:
                if open_ends == 2:
                    score += 20  # Three in a row with two open ends - increased value
                elif open_ends == 1:
                    score += 10  # Three in a row with one open end - increased value
                else:
                    score += 5   # Even blocked three in a row has some value
            elif consecutive == 2:
                if open_ends == 2:
                    score += 8   # Two in a row with two open ends - increased value
                elif open_ends == 1:
                    score += 3   # Two in a row with one open end
        
        # Add proximity score to encourage AI to play near existing pieces
        # This is especially important for the first few moves
        opponent = 'BLACK' if player == 'WHITE' else 'WHITE'
        proximity_score = 0
        
        # Count the number of moves made so far to adjust proximity importance
        moves_made = sum(1 for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if self.board[r][c] is not None)
        
        # Proximity is much more important in early game (first few moves)
        # Significantly increased weight for early moves to ensure AI responds to player moves
        proximity_weight = max(50 - moves_made * 5, 10)  # Decreases as more moves are made, but stays significant
        
        # Find the closest opponent piece and give higher score for proximity
        min_distance = float('inf')
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] == opponent:
                    # Manhattan distance to opponent piece
                    distance = abs(row - r) + abs(col - c)
                    min_distance = min(min_distance, distance)
                    
                    # Special case for very close positions (adjacent or diagonal)
                    if distance <= 2:
                        # Strongly prefer positions that are adjacent to opponent pieces
                        proximity_score += proximity_weight * 3
        
        # Convert distance to score (closer = higher score)
        if min_distance != float('inf'):
            # Score is higher for positions closer to opponent pieces
            # For the first move response, this strongly encourages playing nearby
            proximity_score = proximity_weight * (15 - min(min_distance, 15))
            
            # Extra bonus for positions that are very close to opponent pieces
            if min_distance <= 1:
                proximity_score *= 2  # Double the score for adjacent positions
            
            score += proximity_score
        
        return score
    
    def save_game(self, filename='saved_game.json'):
        """Save the current game state to a file"""
        game_state = {
            'board': self.board,
            'current_player': self.current_player,
            'game_over': self.game_over,
            'winner': self.winner,
            'last_move': self.last_move,
            'vs_ai': self.vs_ai,
            'ai_player': self.ai_player,
            'difficulty': self.difficulty,
            'player_times': self.player_times,
            'move_history': self.move_history
        }
        
        # Convert None values to 'None' string for JSON serialization
        serializable_state = json.dumps(game_state, default=lambda o: 'None' if o is None else o)
        
        with open(filename, 'w') as f:
            f.write(serializable_state)
        
        return True
    
    def load_game(self, filename='saved_game.json'):
        """Load a game state from a file"""
        if not os.path.exists(filename):
            return False
        
        try:
            with open(filename, 'r') as f:
                serialized_state = f.read()
            
            game_state = json.loads(serialized_state)
            
            # Convert 'None' strings back to None
            def deserialize(obj):
                if isinstance(obj, dict):
                    return {k: deserialize(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [deserialize(item) for item in obj]
                elif obj == 'None':
                    return None
                else:
                    return obj
            
            game_state = deserialize(game_state)
            
            # Restore game state
            self.board = game_state['board']
            self.current_player = game_state['current_player']
            self.game_over = game_state['game_over']
            self.winner = game_state['winner']
            self.last_move = game_state['last_move']
            self.vs_ai = game_state['vs_ai']
            self.ai_player = game_state['ai_player']
            self.difficulty = game_state['difficulty']
            self.player_times = game_state['player_times']
            self.move_history = game_state['move_history']
            
            # Reset the last move time to now
            self.last_move_time = pygame.time.get_ticks()
            
            return True
        except Exception as e:
            print(f"Error loading game: {e}")
            return False

def update_display_sizes(new_width, new_height):
    """Update all display-related sizes when window is resized"""
    global WIDTH, HEIGHT, GRID_SIZE, board_offset_x, board_offset_y, side_panel_width
    
    WIDTH, HEIGHT = new_width, new_height
    
    # Calculate new sizes based on window dimensions
    side_panel_width = int(WIDTH * 0.2)  # 20% of width for side panel
    board_area_width = WIDTH - side_panel_width
    
    # Calculate base grid size without zoom
    base_grid_size = int(min(board_area_width, HEIGHT * 0.8) // (BOARD_SIZE + 1))
    
    # Apply zoom to grid size
    GRID_SIZE = int(base_grid_size * zoom_level)
    
    # Center the board in the available area
    board_width = GRID_SIZE * (BOARD_SIZE + 1)
    board_offset_x = (board_area_width - board_width) // 2
    board_offset_y = (HEIGHT - board_width) // 2

def draw_board():
    """Draw the game board"""
    # Draw board background
    board_width = GRID_SIZE * (BOARD_SIZE + 1)
    board_rect = pygame.Rect(board_offset_x, board_offset_y, board_width, board_width)
    pygame.draw.rect(screen, BROWN, board_rect)
    
    # Draw grid lines
    for i in range(1, BOARD_SIZE + 1):
        # Vertical lines
        pygame.draw.line(screen, BLACK, 
                        (board_offset_x + i * GRID_SIZE, board_offset_y + GRID_SIZE), 
                        (board_offset_x + i * GRID_SIZE, board_offset_y + board_width - GRID_SIZE), 2)
        # Horizontal lines
        pygame.draw.line(screen, BLACK, 
                        (board_offset_x + GRID_SIZE, board_offset_y + i * GRID_SIZE), 
                        (board_offset_x + board_width - GRID_SIZE, board_offset_y + i * GRID_SIZE), 2)
    
    # Draw center dot and corner dots
    center = BOARD_SIZE // 2 + 1
    dots = [(center, center), (4, 4), (4, BOARD_SIZE - 3), 
            (BOARD_SIZE - 3, 4), (BOARD_SIZE - 3, BOARD_SIZE - 3)]
    
    for dot in dots:
        pygame.draw.circle(screen, BLACK, 
                          (board_offset_x + dot[0] * GRID_SIZE, board_offset_y + dot[1] * GRID_SIZE), 5)

def draw_pieces(game):
    """Draw the pieces on the board"""
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if game.board[row][col] is not None:
                color = BLACK if game.board[row][col] == 'BLACK' else WHITE
                pygame.draw.circle(screen, color, 
                                 (board_offset_x + (col + 1) * GRID_SIZE, board_offset_y + (row + 1) * GRID_SIZE), 
                                 GRID_SIZE // 2 - 2)
                
                # Draw a border for white pieces to make them more visible
                if game.board[row][col] == 'WHITE':
                    pygame.draw.circle(screen, BLACK, 
                                     (board_offset_x + (col + 1) * GRID_SIZE, board_offset_y + (row + 1) * GRID_SIZE), 
                                     GRID_SIZE // 2 - 2, 1)
    
    # Highlight the last move
    if game.last_move:
        row, col = game.last_move
        pygame.draw.rect(screen, RED, 
                        (board_offset_x + (col + 1) * GRID_SIZE - 5, board_offset_y + (row + 1) * GRID_SIZE - 5, 10, 10), 2)

def draw_side_panel(game):
    """Draw the side panel with game information"""
    # Draw side panel background
    panel_rect = pygame.Rect(WIDTH - side_panel_width, 0, side_panel_width, HEIGHT)
    pygame.draw.rect(screen, LIGHT_GRAY, panel_rect)
    pygame.draw.line(screen, BLACK, (WIDTH - side_panel_width, 0), (WIDTH - side_panel_width, HEIGHT), 2)
    
    # Draw game status and information - scale font sizes with zoom level
    font_size = int(32 * min(1.5, max(0.8, zoom_level)))
    small_font_size = int(24 * min(1.5, max(0.8, zoom_level)))
    font = pygame.font.Font(None, font_size)
    small_font = pygame.font.Font(None, small_font_size)
    
    # Initialize sub_text with an empty string
    sub_text = ""
    
    # Game status
    if game.game_over:
        if game.winner:
            text = f"{game.winner} WINS!"
        else:
            text = "DRAW!"
    else:
        if game.multiplayer:
            text = f"Player: {game.current_player}"
            sub_text = f"(You: {game.player_color})"
        elif game.vs_ai and game.current_player == game.ai_player:
            text = f"AI is thinking..."
            sub_text = f"Difficulty: {game.difficulty}"
        else:
            text = f"Player: {game.current_player}"
            sub_text = ""
    
    # Display game status
    y_pos = 20
    text_surface = font.render(text, True, BLACK)
    text_rect = text_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
    screen.blit(text_surface, text_rect)
    
    if sub_text:
        y_pos += 30
        sub_text_surface = small_font.render(sub_text, True, BLACK)
        sub_text_rect = sub_text_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
        screen.blit(sub_text_surface, sub_text_rect)
    
    # Game timer
    y_pos += 50
    current_time = pygame.time.get_ticks()
    game_time = (current_time - game.game_start_time) // 1000  # Convert to seconds
    minutes, seconds = divmod(game_time, 60)
    
    # Update current player's time
    if not game.game_over and game.last_move_time > 0:
        player_time = game.player_times[game.current_player] + (current_time - game.last_move_time)
    else:
        player_time = game.player_times[game.current_player]
    
    player_minutes, player_seconds = divmod(player_time // 1000, 60)
    
    # Display game time
    time_text = f"Game Time: {minutes:02d}:{seconds:02d}"
    time_surface = small_font.render(time_text, True, BLACK)
    time_rect = time_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
    screen.blit(time_surface, time_rect)
    
    # Display player times
    y_pos += 30
    black_minutes, black_seconds = divmod(game.player_times['BLACK'] // 1000, 60)
    white_minutes, white_seconds = divmod(game.player_times['WHITE'] // 1000, 60)
    
    black_time_text = f"Black: {black_minutes:02d}:{black_seconds:02d}"
    white_time_text = f"White: {white_minutes:02d}:{white_seconds:02d}"
    
    black_time_surface = small_font.render(black_time_text, True, BLACK)
    white_time_surface = small_font.render(white_time_text, True, BLACK)
    
    black_time_rect = black_time_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
    screen.blit(black_time_surface, black_time_rect)
    
    y_pos += 25
    white_time_rect = white_time_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
    screen.blit(white_time_surface, white_time_rect)
    
    # Zoom instructions
    y_pos += 50
    zoom_text = f"Zoom: {zoom_level:.1f}x"
    zoom_surface = small_font.render(zoom_text, True, BLACK)
    zoom_rect = zoom_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
    screen.blit(zoom_surface, zoom_rect)
    
    y_pos += 25
    help_text = "Mouse wheel to zoom"
    help_surface = small_font.render(help_text, True, BLACK)
    help_rect = help_surface.get_rect(center=(WIDTH - side_panel_width//2, y_pos))
    screen.blit(help_surface, help_rect)

def draw_buttons(buttons):
    """Draw all UI buttons"""
    for button in buttons:
        button.draw()

# Network Manager for multiplayer functionality
class NetworkManager:
    def __init__(self, game, is_host=False, server_ip='localhost', port=5555):
        self.game = game
        self.is_host = is_host
        self.server_ip = server_ip
        self.port = port
        self.socket = None
        self.connection = None
        self.client_address = None
        self.connected = False
        self.running = True
        self.receive_thread = None
    
    def start_server(self):
        """Start a server to host a game"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind(('', self.port))
            self.socket.listen(1)
            self.socket.settimeout(0.5)  # Non-blocking with timeout
            
            # Set game to multiplayer mode
            self.game.multiplayer = True
            self.game.is_host = True
            self.game.player_color = 'BLACK'  # Host plays as BLACK
            
            # Start a thread to accept connections
            accept_thread = threading.Thread(target=self.accept_connections)
            accept_thread.daemon = True
            accept_thread.start()
            
            return True
        except Exception as e:
            print(f"Error starting server: {e}")
            return False
    
    def accept_connections(self):
        """Accept incoming connections (server mode)"""
        print("Waiting for opponent to connect...")
        while self.running and not self.connected:
            try:
                self.connection, self.client_address = self.socket.accept()
                self.connected = True
                print(f"Connected to: {self.client_address}")
                
                # Start receiving thread
                self.receive_thread = threading.Thread(target=self.receive_data)
                self.receive_thread.daemon = True
                self.receive_thread.start()
                
                # Send initial game state
                self.send_game_state()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error accepting connection: {e}")
                break
    
    def connect_to_server(self):
        """Connect to a server as a client"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_ip, self.port))
            self.connected = True
            
            # Set game to multiplayer mode
            self.game.multiplayer = True
            self.game.is_host = False
            self.game.player_color = 'WHITE'  # Client plays as WHITE
            
            # Start receiving thread
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            
            return True
        except Exception as e:
            print(f"Error connecting to server: {e}")
            return False
    
    def send_game_state(self):
        """Send the current game state to the other player"""
        if not self.connected:
            return False
        
        try:
            # Create a serializable game state
            game_state = {
                'board': self.game.board,
                'current_player': self.game.current_player,
                'game_over': self.game.game_over,
                'winner': self.game.winner,
                'last_move': self.game.last_move
            }
            
            # Serialize and send
            data = pickle.dumps(game_state)
            
            if self.is_host:
                self.connection.sendall(data)
            else:
                self.socket.sendall(data)
            
            return True
        except Exception as e:
            print(f"Error sending data: {e}")
            self.connected = False
            return False
    
    def send_move(self, row, col):
        """Send a move to the other player"""
        if not self.connected:
            return False
        
        try:
            # Create a move data packet
            move_data = {
                'type': 'move',
                'row': row,
                'col': col
            }
            
            # Serialize and send
            data = pickle.dumps(move_data)
            
            if self.is_host:
                self.connection.sendall(data)
            else:
                self.socket.sendall(data)
            
            return True
        except Exception as e:
            print(f"Error sending move: {e}")
            self.connected = False
            return False
    
    def receive_data(self):
        """Receive data from the other player"""
        socket_to_use = self.connection if self.is_host else self.socket
        
        while self.running and self.connected:
            try:
                data = socket_to_use.recv(4096)
                if not data:
                    print("Connection closed by peer")
                    self.connected = False
                    break
                
                # Deserialize the data
                received_data = pickle.loads(data)
                
                # Process based on data type
                if isinstance(received_data, dict):
                    if 'type' in received_data and received_data['type'] == 'move':
                        # It's a move
                        row, col = received_data['row'], received_data['col']
                        
                        # Update the game (on the main thread)
                        pygame.event.post(pygame.event.Event(
                            pygame.USEREVENT, 
                            {"action": "network_move", "row": row, "col": col}
                        ))
                    else:
                        # It's a full game state
                        pygame.event.post(pygame.event.Event(
                            pygame.USEREVENT, 
                            {"action": "update_game_state", "state": received_data}
                        ))
            except Exception as e:
                print(f"Error receiving data: {e}")
                self.connected = False
                break
    
    def close(self):
        """Close the network connection"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.connection:
            self.connection.close()
        self.connected = False

def main():
    game = Game()
    clock = pygame.time.Clock()
    
    # Update initial display sizes
    update_display_sizes(BASE_WIDTH, BASE_HEIGHT)
    
    # Create buttons
    button_width, button_height = 120, 40
    small_button_width = 80
    button_margin = 10
    
    # Main control buttons
    restart_button = Button(0, 0, button_width, button_height, "Restart", GREEN)
    exit_button = Button(0, 0, button_width, button_height, "Exit", RED)
    mode_button = Button(0, 0, button_width, button_height, "vs AI: ON", GRAY)
    
    # Game feature buttons
    undo_button = Button(0, 0, small_button_width, button_height, "Undo", GRAY)
    save_button = Button(0, 0, small_button_width, button_height, "Save", GRAY)
    load_button = Button(0, 0, small_button_width, button_height, "Load", GRAY)
    
    # Difficulty button
    difficulty_button = Button(0, 0, small_button_width, button_height, game.difficulty, GRAY)
    
    # Network multiplayer buttons
    host_button = Button(0, 0, small_button_width, button_height, "Host", GRAY)
    join_button = Button(0, 0, small_button_width, button_height, "Join", GRAY)
    
    # Collect all buttons
    buttons = [restart_button, exit_button, mode_button, undo_button, 
               save_button, load_button, difficulty_button, host_button, join_button]
    
    # Initialize network manager as None
    network = None
    
    # Calculate button positions based on window size
    def update_button_positions():
        # Bottom control panel
        panel_height = 60
        panel_y = HEIGHT - panel_height
        
        # Main control buttons (centered at bottom)
        restart_button.rect.x = (WIDTH - side_panel_width - button_width * 3 - button_margin * 2) // 2
        restart_button.rect.y = panel_y + (panel_height - button_height) // 2
        
        mode_button.rect.x = restart_button.rect.x + button_width + button_margin
        mode_button.rect.y = panel_y + (panel_height - button_height) // 2
        
        exit_button.rect.x = mode_button.rect.x + button_width + button_margin
        exit_button.rect.y = panel_y + (panel_height - button_height) // 2
        
        # Side panel buttons
        side_panel_x = WIDTH - side_panel_width + (side_panel_width - small_button_width) // 2
        button_y_start = HEIGHT // 2
        
        # Game feature buttons
        undo_button.rect.x = side_panel_x
        undo_button.rect.y = button_y_start
        
        save_button.rect.x = side_panel_x
        save_button.rect.y = button_y_start + button_height + button_margin
        
        load_button.rect.x = side_panel_x
        load_button.rect.y = button_y_start + (button_height + button_margin) * 2
        
        # Difficulty button
        difficulty_button.rect.x = side_panel_x
        difficulty_button.rect.y = button_y_start + (button_height + button_margin) * 3
        
        # Network multiplayer buttons
        host_button.rect.x = side_panel_x
        host_button.rect.y = button_y_start + (button_height + button_margin) * 4
        
        join_button.rect.x = side_panel_x
        join_button.rect.y = button_y_start + (button_height + button_margin) * 5
    
    # Initial button positioning
    update_button_positions()
    
    while True:
        mouse_pos = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # Close network connection if active
                if network:
                    network.close()
                pygame.quit()
                sys.exit()
            
            elif event.type == pygame.VIDEORESIZE:
                # Update window and board sizes
                update_display_sizes(event.w, event.h)
                update_button_positions()
            
            elif event.type == pygame.MOUSEWHEEL:
                # Handle zoom with mouse wheel
                global zoom_level
                old_zoom = zoom_level
                zoom_level = max(MIN_ZOOM, min(MAX_ZOOM, zoom_level + event.y * 0.1))
                if old_zoom != zoom_level:
                    update_display_sizes(WIDTH, HEIGHT)
                    update_button_positions()
            
            # Handle mouse movement for button hover effect
            for button in buttons:
                button.check_hover(mouse_pos)
            
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
                # Check if buttons were clicked
                if restart_button.is_clicked(mouse_pos):
                    game.reset()
                elif exit_button.is_clicked(mouse_pos):
                    # Close network connection if active
                    if network:
                        network.close()
                    pygame.quit()
                    sys.exit()
                elif mode_button.is_clicked(mouse_pos):
                    # Can't change mode in multiplayer
                    if not game.multiplayer:
                        game.vs_ai = not game.vs_ai
                        mode_button.text = "vs AI: ON" if game.vs_ai else "vs AI: OFF"
                        game.reset()
                elif undo_button.is_clicked(mouse_pos):
                    # Can't undo in multiplayer
                    if not game.multiplayer:
                        game.undo_move()
                elif save_button.is_clicked(mouse_pos):
                    game.save_game()
                elif load_button.is_clicked(mouse_pos):
                    # Can't load in multiplayer
                    if not game.multiplayer:
                        game.load_game()
                elif difficulty_button.is_clicked(mouse_pos):
                    # Can't change difficulty in multiplayer
                    if not game.multiplayer:
                        # Cycle through difficulty levels
                        if game.difficulty == 'Easy':
                            game.difficulty = 'Medium'
                        elif game.difficulty == 'Medium':
                            game.difficulty = 'Hard'
                        else:
                            game.difficulty = 'Easy'
                        difficulty_button.text = game.difficulty
                elif host_button.is_clicked(mouse_pos):
                    # Start hosting a game
                    if not game.multiplayer:
                        game.reset()
                        network = NetworkManager(game, is_host=True)
                        if network.start_server():
                            host_button.text = "Hosting"
                            join_button.text = "Cancel"
                            mode_button.text = "Network"
                elif join_button.is_clicked(mouse_pos):
                    if not game.multiplayer:
                        # Join a hosted game
                        server_ip = 'localhost'  # In a real app, you'd prompt for this
                        network = NetworkManager(game, is_host=False, server_ip=server_ip)
                        if network.connect_to_server():
                            join_button.text = "Connected"
                            host_button.text = "Cancel"
                            mode_button.text = "Network"
                    elif network and network.connected:
                        # Cancel connection
                        network.close()
                        network = None
                        game.multiplayer = False
                        game.reset()
                        host_button.text = "Host"
                        join_button.text = "Join"
                        mode_button.text = "vs AI: ON" if game.vs_ai else "vs AI: OFF"
                
                # Handle board clicks for placing pieces
                elif not game.game_over:
                    # In multiplayer, only allow moves on your turn
                    can_move = True
                    if game.multiplayer:
                        can_move = game.current_player == game.player_color
                    elif game.vs_ai:
                        can_move = game.current_player != game.ai_player
                    
                    if can_move:
                        x, y = pygame.mouse.get_pos()
                        # Only process clicks within the board area
                        board_width = GRID_SIZE * (BOARD_SIZE + 1)
                        if (board_offset_x <= x <= board_offset_x + board_width and 
                            board_offset_y <= y <= board_offset_y + board_width):
                            # Convert pixel coordinates to board coordinates more accurately
                            # Use floor division to get the nearest grid intersection
                            col = int((x - board_offset_x + GRID_SIZE/2) // GRID_SIZE) - 1
                            row = int((y - board_offset_y + GRID_SIZE/2) // GRID_SIZE) - 1
                            
                            # Make the move
                            if game.place_piece(row, col):
                                # If in multiplayer, send the move
                                if game.multiplayer and network and network.connected:
                                    network.send_move(row, col)
            
            # Keep the 'R' key restart functionality as an alternative
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:  # 'R' key to restart
                    game.reset()
                elif event.key == pygame.K_u:  # 'U' key to undo
                    game.undo_move()
                elif event.key == pygame.K_s:  # 'S' key to save
                    game.save_game()
                elif event.key == pygame.K_l:  # 'L' key to load
                    game.load_game()
        
        # Clear screen
        screen.fill(WHITE)
        
        # Draw game elements
        draw_board()
        draw_pieces(game)
        draw_side_panel(game)
        draw_buttons(buttons)
        
        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()