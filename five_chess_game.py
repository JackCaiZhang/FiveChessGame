import pygame
import sys
import random
import json
import os
import socket
import threading
import pickle
from collections import defaultdict

# Initialize pygame
pygame.init()

# Constants
WIDTH, HEIGHT = 600, 650  # Increased height for buttons
BOARD_SIZE = 15  # 15x15 grid
GRID_SIZE = WIDTH // (BOARD_SIZE + 1)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BROWN = (210, 180, 140)  # Board color
RED = (255, 0, 0)  # Highlight color
GREEN = (0, 128, 0)  # Button color
GRAY = (128, 128, 128)  # Button color

# Create the screen
screen = pygame.display.set_mode((WIDTH, HEIGHT))
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
            depth = 1  # Less look-ahead
        elif self.difficulty == 'Medium':
            randomness = 5   # Medium randomness
            depth = 2  # Medium look-ahead
        else:  # Hard
            randomness = 1   # Low randomness for hard mode
            depth = 3  # More look-ahead
        
        for row, col in valid_moves:
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
    
    def evaluate_move(self, row, col, depth=2):
        """Evaluate a potential move for the AI with look-ahead based on difficulty"""
        score = 0
        
        # Check if AI can win with this move
        self.board[row][col] = self.ai_player
        if self.check_win(row, col):
            self.board[row][col] = None
            return 1000  # Very high score for winning move
        
        # Check if AI needs to block opponent's winning move
        opponent = 'BLACK' if self.ai_player == 'WHITE' else 'WHITE'
        self.board[row][col] = opponent
        if self.check_win(row, col):
            self.board[row][col] = None
            return 900  # High score for blocking opponent's win
        
        # Reset the cell
        self.board[row][col] = None
        
        # Look ahead for deeper evaluation if depth > 1
        if depth > 1:
            # Temporarily place AI's piece
            self.board[row][col] = self.ai_player
            
            # Check opponent's best response
            min_opponent_score = float('inf')
            
            # Check a few key positions around this move
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    r, c = row + dr, col + dc
                    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] is None:
                        # Evaluate opponent's move with reduced depth
                        opponent_score = self.evaluate_move(r, c, depth - 1)
                        min_opponent_score = min(min_opponent_score, opponent_score)
            
            # Reset the cell
            self.board[row][col] = None
            
            # Adjust score based on opponent's best response
            if min_opponent_score < float('inf'):
                score -= min_opponent_score * 0.5  # Discount opponent's advantage
        
        # Evaluate position based on patterns around this move
        directions = [
            [(0, 1), (0, -1)],   # Horizontal
            [(1, 0), (-1, 0)],   # Vertical
            [(1, 1), (-1, -1)],  # Diagonal \
            [(1, -1), (-1, 1)]   # Diagonal /
        ]
        
        for dir_pair in directions:
            # Count AI's pieces and empty spaces in this direction
            ai_count = 0
            empty_count = 1  # Count the current empty cell
            
            for dx, dy in dir_pair:
                for i in range(1, 5):
                    r, c = row + dx * i, col + dy * i
                    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                        if self.board[r][c] == self.ai_player:
                            ai_count += 1
                        elif self.board[r][c] is None:
                            empty_count += 1
                        else:
                            break
                    else:
                        break
            
            # Score based on potential to form a line
            if ai_count >= 3 and empty_count >= 5:
                score += 50 * ai_count
            elif ai_count >= 2 and empty_count >= 5:
                score += 10 * ai_count
            elif empty_count >= 5:
                score += 5
        
        # Prefer center and areas near existing pieces
        center_distance = abs(row - BOARD_SIZE // 2) + abs(col - BOARD_SIZE // 2)
        score -= center_distance  # Prefer center
        
        # Check if move is adjacent to existing pieces
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                r, c = row + dr, col + dc
                if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] is not None:
                    score += 5  # Bonus for moves adjacent to existing pieces
        
        return score
    
    def check_win(self, row, col):
        """Check if the current player has won after placing a piece"""
        player = self.board[row][col]
        directions = [
            [(0, 1), (0, -1)],   # Horizontal
            [(1, 0), (-1, 0)],   # Vertical
            [(1, 1), (-1, -1)],  # Diagonal \
            [(1, -1), (-1, 1)]   # Diagonal /
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

def draw_board():
    """Draw the game board"""
    screen.fill(BROWN)
    
    # Draw grid lines
    for i in range(1, BOARD_SIZE + 1):
        # Vertical lines
        pygame.draw.line(screen, BLACK, 
                        (i * GRID_SIZE, GRID_SIZE), 
                        (i * GRID_SIZE, HEIGHT - GRID_SIZE), 2)
        # Horizontal lines
        pygame.draw.line(screen, BLACK, 
                        (GRID_SIZE, i * GRID_SIZE), 
                        (WIDTH - GRID_SIZE, i * GRID_SIZE), 2)
    
    # Draw center dot and corner dots
    center = BOARD_SIZE // 2 + 1
    dots = [(center, center), (4, 4), (4, BOARD_SIZE - 3), 
            (BOARD_SIZE - 3, 4), (BOARD_SIZE - 3, BOARD_SIZE - 3)]
    
    for dot in dots:
        pygame.draw.circle(screen, BLACK, 
                          (dot[0] * GRID_SIZE, dot[1] * GRID_SIZE), 5)

def draw_pieces(game):
    """Draw the pieces on the board"""
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if game.board[row][col] is not None:
                color = BLACK if game.board[row][col] == 'BLACK' else WHITE
                pygame.draw.circle(screen, color, 
                                 ((col + 1) * GRID_SIZE, (row + 1) * GRID_SIZE), 
                                 GRID_SIZE // 2 - 2)
                
                # Draw a border for white pieces to make them more visible
                if game.board[row][col] == 'WHITE':
                    pygame.draw.circle(screen, BLACK, 
                                     ((col + 1) * GRID_SIZE, (row + 1) * GRID_SIZE), 
                                     GRID_SIZE // 2 - 2, 1)
    
    # Highlight the last move
    if game.last_move:
        row, col = game.last_move
        pygame.draw.rect(screen, RED, 
                        ((col + 1) * GRID_SIZE - 5, (row + 1) * GRID_SIZE - 5, 10, 10), 2)

def draw_status(game):
    """Draw the game status and timer"""
    font = pygame.font.Font(None, 36)
    small_font = pygame.font.Font(None, 24)
    
    # Game status
    if game.game_over:
        if game.winner:
            text = f"{game.winner} WINS!"
        else:
            text = "DRAW!"
    else:
        if game.multiplayer:
            text = f"Current Player: {game.current_player} (You: {game.player_color})"
        elif game.vs_ai and game.current_player == game.ai_player:
            text = f"AI ({game.difficulty}) is thinking..."
        else:
            text = f"Current Player: {game.current_player}"
    
    text_surface = font.render(text, True, BLACK)
    text_rect = text_surface.get_rect(center=(WIDTH // 2, 30))
    pygame.draw.rect(screen, BROWN, text_rect)
    screen.blit(text_surface, text_rect)
    
    # Game timer
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
    screen.blit(time_surface, (10, 10))
    
    # Display player times
    black_minutes, black_seconds = divmod(game.player_times['BLACK'] // 1000, 60)
    white_minutes, white_seconds = divmod(game.player_times['WHITE'] // 1000, 60)
    
    black_time_text = f"Black: {black_minutes:02d}:{black_seconds:02d}"
    white_time_text = f"White: {white_minutes:02d}:{white_seconds:02d}"
    
    black_time_surface = small_font.render(black_time_text, True, BLACK)
    white_time_surface = small_font.render(white_time_text, True, BLACK)
    
    screen.blit(black_time_surface, (WIDTH - 120, 10))
    screen.blit(white_time_surface, (WIDTH - 120, 30))

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
    
    # Create buttons
    button_width, button_height = 120, 40
    small_button_width = 80
    
    # Main control buttons
    restart_button = Button(WIDTH // 2 - 180, HEIGHT - 50, button_width, button_height, "Restart", GREEN)
    exit_button = Button(WIDTH // 2 + 60, HEIGHT - 50, button_width, button_height, "Exit", RED)
    mode_button = Button(WIDTH // 2 - 60, HEIGHT - 50, button_width, button_height, "vs AI: ON", GRAY)
    
    # Game feature buttons
    undo_button = Button(10, HEIGHT - 100, small_button_width, button_height, "Undo", GRAY)
    save_button = Button(100, HEIGHT - 100, small_button_width, button_height, "Save", GRAY)
    load_button = Button(190, HEIGHT - 100, small_button_width, button_height, "Load", GRAY)
    
    # Difficulty buttons
    difficulty_button = Button(WIDTH - 90, HEIGHT - 100, small_button_width, button_height, game.difficulty, GRAY)
    
    # Network multiplayer buttons
    host_button = Button(280, HEIGHT - 100, small_button_width, button_height, "Host", GRAY)
    join_button = Button(370, HEIGHT - 100, small_button_width, button_height, "Join", GRAY)
    
    # Collect all buttons
    buttons = [restart_button, exit_button, mode_button, undo_button, 
               save_button, load_button, difficulty_button, host_button, join_button]
    
    # Initialize network manager as None
    network = None
    
    while True:
        mouse_pos = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # Close network connection if active
                if network:
                    network.close()
                pygame.quit()
                sys.exit()
            
            # Handle custom network events
            if event.type == pygame.USEREVENT:
                if event.action == "network_move":
                    # Process move received from network
                    game.place_piece(event.row, event.col)
                elif event.action == "update_game_state":
                    # Update game state from network
                    game.board = event.state['board']
                    game.current_player = event.state['current_player']
                    game.game_over = event.state['game_over']
                    game.winner = event.state['winner']
                    game.last_move = event.state['last_move']
            
            # Handle mouse movement for button hover effect
            for button in buttons:
                button.check_hover(mouse_pos)
            
            if event.type == pygame.MOUSEBUTTONDOWN:
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
                        if GRID_SIZE <= x <= WIDTH - GRID_SIZE and GRID_SIZE <= y <= WIDTH - GRID_SIZE:
                            # Convert pixel coordinates to board coordinates
                            col = round(x / GRID_SIZE) - 1
                            row = round(y / GRID_SIZE) - 1
                            
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
        
        draw_board()
        draw_pieces(game)
        draw_status(game)
        draw_buttons(buttons)
        
        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()