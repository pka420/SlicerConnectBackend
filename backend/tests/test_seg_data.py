"""
WebSocket Test Client for Collaborative Segmentation
Tests delta and full segmentation updates without needing 3D Slicer

Usage:
    python test_websocket_client.py

Before running:
    1. Start the FastAPI server: python fastapi_backend.py
    2. Fill in your TOKEN below
    3. Run this script
"""

import asyncio
import websockets
import json
import numpy as np
import base64
import zlib
from datetime import datetime
import argparse

TOKEN = ''
WS_URL = "ws://localhost:8000/collaboration/sessions"
SESSION_ID = 2

DIMENSIONS = [64, 64, 32] 
SPACING = [1.0, 1.0, 1.0]
ORIGIN = [0.0, 0.0, 0.0]
DATA_TYPE = "uint8"

def create_empty_segmentation():
    """Create an empty segmentation array"""
    shape = (DIMENSIONS[2], DIMENSIONS[1], DIMENSIONS[0]) 
    return np.zeros(shape, dtype=DATA_TYPE)


def create_test_segmentation():
    """Create a test segmentation with some shapes"""
    array = create_empty_segmentation()
    
    center = (DIMENSIONS[2]//2, DIMENSIONS[1]//2, DIMENSIONS[0]//2)
    radius = 10
    
    for z in range(DIMENSIONS[2]):
        for y in range(DIMENSIONS[1]):
            for x in range(DIMENSIONS[0]):
                dist = np.sqrt((z - center[0])**2 + 
                             (y - center[1])**2 + 
                             (x - center[2])**2)
                if dist < radius:
                    array[z, y, x] = 1
    
    print(f"Created test segmentation: {np.count_nonzero(array)} voxels")
    return array


def decode_full_segmentation(data):
    """Decode received full segmentation"""
    compressed = base64.b64decode(data["imageData"])
    decompressed = zlib.decompress(compressed)
    
    dims = data["dimensions"]
    dtype = data["dataType"]
    array = np.frombuffer(decompressed, dtype=dtype)
    array = array.reshape(dims[2], dims[1], dims[0])
    
    return array


def create_delta_update(old_array, new_array):
    """Create a delta update between two arrays"""
    # Find changed voxels
    changed_mask = old_array != new_array
    
    if not np.any(changed_mask):
        return None
    
    # Get indices and values of changed voxels
    changed_indices = np.argwhere(changed_mask)
    changed_values = new_array[changed_mask]
    
    num_changes = len(changed_indices)
    
    # Compress
    indices_bytes = changed_indices.astype(np.uint16).tobytes()
    values_bytes = changed_values.tobytes()
    
    compressed_indices = zlib.compress(indices_bytes)
    compressed_values = zlib.compress(values_bytes)
    
    encoded_indices = base64.b64encode(compressed_indices).decode('utf-8')
    encoded_values = base64.b64encode(compressed_values).decode('utf-8')
    
    return {
        "indices": encoded_indices,
        "values": encoded_values,
        "numChanges": num_changes,
        "dimensions": DIMENSIONS,
        "spacing": SPACING,
        "origin": ORIGIN,
        "dataType": DATA_TYPE
    }


def decode_delta_update(data):
    """Decode a delta update"""
    compressed_indices = base64.b64decode(data["indices"])
    compressed_values = base64.b64decode(data["values"])
    
    indices_bytes = zlib.decompress(compressed_indices)
    values_bytes = zlib.decompress(compressed_values)
    
    indices = np.frombuffer(indices_bytes, dtype=np.uint16).reshape(-1, 3)
    values = np.frombuffer(values_bytes, dtype=data["dataType"])
    
    return indices, values


def apply_delta(array, indices, values):
    """Apply delta update to array"""
    for idx, value in zip(indices, values):
        array[idx[0], idx[1], idx[2]] = value
    return array


def paint_brush_stroke(array, start_pos, end_pos, radius=2, value=1):
    """Simulate a brush stroke on the segmentation"""
    # Linear interpolation between start and end
    steps = 20
    modified = array.copy()
    
    for i in range(steps):
        t = i / steps
        pos = (
            int(start_pos[0] + t * (end_pos[0] - start_pos[0])),
            int(start_pos[1] + t * (end_pos[1] - start_pos[1])),
            int(start_pos[2] + t * (end_pos[2] - start_pos[2]))
        )
        
        # Paint sphere around position
        for dz in range(-radius, radius+1):
            for dy in range(-radius, radius+1):
                for dx in range(-radius, radius+1):
                    if dz*dz + dy*dy + dx*dx <= radius*radius:
                        z, y, x = pos[0]+dz, pos[1]+dy, pos[2]+dx
                        if (0 <= z < DIMENSIONS[2] and 
                            0 <= y < DIMENSIONS[1] and 
                            0 <= x < DIMENSIONS[0]):
                            modified[z, y, x] = value
    
    return modified


# ============================================================================
# WebSocket Client
# ============================================================================

class SegmentationClient:
    def __init__(self, user_id="test_user"):
        self.user_id = user_id
        self.ws = None
        self.current_segmentation = create_empty_segmentation()
        self.message_count = 0
        
    async def connect(self):
        """Connect to WebSocket server"""
        url = f"{WS_URL}/{SESSION_ID}/ws?token={TOKEN}"
        print(f"Connecting to: {url}")
        
        try:
            self.ws = await websockets.connect(url)
            print(f"✓ Connected as {self.user_id}")
            
            # Send join message
            await self.send_join()
            
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from server"""
        if self.ws:
            await self.ws.close()
            print("Disconnected")
    
    async def send_join(self):
        """Send join message"""
        message = {
            "type": "join",
            "userId": self.user_id,
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
        }
        await self.ws.send(json.dumps(message))
        print(f"→ Sent join message")
    
    async def send_full_segmentation(self, array):
        """Send full segmentation"""
        import zlib
        compressor = zlib.compressobj(
                level=zlib.Z_DEFAULT_COMPRESSION, 
                method=zlib.DEFLATED, 
                wbits=15, 
                memLevel=8, 
                strategy=zlib.Z_RLE
        )
        compressedData = compressor.compress(array.tobytes())
        compressedData += compressor.flush()

        encodedData = base64.b64encode(compressedData).decode('utf-8')
        message = {
            "type": "segmentation_full",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "imageData": encodedData,
                "dimensions": DIMENSIONS,
                "spacing": SPACING,
                "origin": ORIGIN,
                "dataType": DATA_TYPE
            }
        }

        await self.ws.send(json.dumps(message))
        self.message_count += 1
        
        non_zero = np.count_nonzero(array)
        print(f"→ Sent full segmentation #{self.message_count} ({non_zero} non-zero voxels)")
    
    async def send_delta(self, new_array):
        """Send delta update"""
        delta_data = create_delta_update(self.current_segmentation, new_array)
        
        if delta_data is None:
            print("  No changes to send")
            return
        
        message = {
            "type": "segmentation_delta",
            "userId": self.user_id,
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "data": delta_data
        }
        
        await self.ws.send(json.dumps(message))
        self.message_count += 1
        
        print(f"→ Sent delta #{self.message_count} ({delta_data['numChanges']} voxels changed)")
        
        # Update current state
        self.current_segmentation = new_array.copy()
    
    async def receive_messages(self, duration=5):
        """Receive messages for a specified duration"""
        print(f"\nListening for messages for {duration} seconds...")
        
        try:
            end_time = asyncio.get_event_loop().time() + duration
            
            while asyncio.get_event_loop().time() < end_time:
                try:
                    message_text = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                    message = json.loads(message_text)
                    
                    msg_type = message.get("type")
                    user = message.get("userId", "unknown")
                    
                    if msg_type == "segmentation_full":
                        array = decode_full_segmentation(message["data"])
                        non_zero = np.count_nonzero(array)
                        print(f"← Received full segmentation from {user} ({non_zero} voxels)")
                        self.current_segmentation = array
                    
                    elif msg_type == "segmentation_delta":
                        indices, values = decode_delta_update(message["data"])
                        self.current_segmentation = apply_delta(
                            self.current_segmentation, indices, values
                        )
                        print(f"← Received delta from {user} ({len(values)} voxels)")
                    
                    elif msg_type == "user_joined":
                        print(f"← User joined: {user} (total: {message.get('totalUsers')})")
                    
                    elif msg_type == "user_left":
                        print(f"← User left: {user} (total: {message.get('totalUsers')})")
                    
                    else:
                        print(f"← Received: {msg_type} from {user}")
                
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server")
                    break
        
        except Exception as e:
            print(f"Error receiving messages: {e}")


# ============================================================================
# Test Scenarios
# ============================================================================

async def test_full_segmentation():
    """Test sending full segmentation"""
    print("\n" + "="*60)
    print("TEST 1: Sending Full Segmentation")
    print("="*60)
    
    client = SegmentationClient(user_id="test_full")
    
    if not await client.connect():
        return
    
    array = create_test_segmentation()
    await client.send_full_segmentation(array)
    await client.receive_messages(duration=3)
    await client.disconnect()


async def test_delta_updates():
    """Test sending delta updates (simulating brush strokes)"""
    print("\n" + "="*60)
    print("TEST 2: Sending Delta Updates (Brush Strokes)")
    print("="*60)
    
    client = SegmentationClient(user_id="test_delta")
    
    if not await client.connect():
        return
    
    # Start with empty segmentation
    current = create_empty_segmentation()
    
    # Send initial full segmentation
    await client.send_full_segmentation(current)
    await asyncio.sleep(0.5)
    
    # Simulate 5 brush strokes
    print("\nSimulating brush strokes...")
    
    brush_strokes = [
        ((10, 10, 10), (15, 15, 15)),  # Diagonal stroke
        ((20, 20, 20), (25, 20, 20)),  # Horizontal stroke
        ((30, 30, 15), (30, 30, 20)),  # Vertical stroke
        ((15, 25, 15), (20, 30, 20)),  # Another diagonal
        ((25, 15, 15), (25, 20, 20)),  # Small stroke
    ]
    
    for i, (start, end) in enumerate(brush_strokes, 1):
        print(f"\nBrush stroke {i}:")
        new_array = paint_brush_stroke(current, start, end, radius=2, value=1)
        
        await client.send_delta(new_array)
        current = new_array
        
        await asyncio.sleep(0.5)
    
    # Listen for any responses
    await client.receive_messages(duration=2)
    
    await client.disconnect()


async def test_two_clients():
    """Test two clients collaborating"""
    print("\n" + "="*60)
    print("TEST 3: Two Clients Collaborating")
    print("="*60)
    
    client1 = SegmentationClient(user_id="alice")
    client2 = SegmentationClient(user_id="bob")
    
    if not await client1.connect() or not await client2.connect():
        return
    
    await asyncio.sleep(1)
    
    # Client 1 sends initial segmentation
    print("\n[Alice] Creating initial segmentation...")
    array1 = create_empty_segmentation()
    array1 = paint_brush_stroke(array1, (10, 10, 10), (20, 20, 20), radius=3, value=1)
    await client1.send_full_segmentation(array1)
    
    await asyncio.sleep(1)
    
    # Client 2 adds to it
    print("\n[Bob] Adding brush stroke...")
    array2 = array1.copy()
    array2 = paint_brush_stroke(array2, (30, 30, 15), (40, 40, 25), radius=3, value=2)
    await client2.send_delta(array2)
    
    await asyncio.sleep(1)
    
    # Client 1 adds more
    print("\n[Alice] Adding another stroke...")
    array1 = paint_brush_stroke(array1, (25, 15, 15), (35, 25, 25), radius=2, value=1)
    await client1.send_delta(array1)
    
    # Both listen for updates
    print("\n[Both] Listening for updates...")
    await asyncio.gather(
        client1.receive_messages(duration=3),
        client2.receive_messages(duration=3)
    )
    
    await client1.disconnect()
    await client2.disconnect()


async def test_large_change():
    """Test switching between delta and full segmentation"""
    print("\n" + "="*60)
    print("TEST 4: Large Change (Delta vs Full)")
    print("="*60)
    
    client = SegmentationClient(user_id="test_large")
    
    if not await client.connect():
        return
    
    # Start with small segmentation
    print("\nSending initial small segmentation...")
    small = create_empty_segmentation()
    small = paint_brush_stroke(small, (10, 10, 10), (15, 15, 15), radius=2, value=1)
    await client.send_full_segmentation(small)
    
    await asyncio.sleep(0.5)
    
    # Small change (delta)
    print("\nMaking small change (should use delta)...")
    small_change = paint_brush_stroke(small, (20, 20, 20), (22, 22, 22), radius=1, value=1)
    await client.send_delta(small_change)
    
    await asyncio.sleep(0.5)
    
    # Large change (should trigger full send in real implementation)
    print("\nMaking large change (>30% different)...")
    large_change = create_test_segmentation()  # Completely different
    
    # Calculate difference
    diff_mask = small_change != large_change
    percent_changed = (np.count_nonzero(diff_mask) / small_change.size) * 100
    print(f"Changed: {percent_changed:.1f}% of voxels")
    
    if percent_changed > 30:
        print("→ Using full segmentation (>30% changed)")
        await client.send_full_segmentation(large_change)
    else:
        print("→ Using delta (<30% changed)")
        await client.send_delta(large_change)
    
    await client.receive_messages(duration=2)
    await client.disconnect()


async def interactive_mode():
    """Interactive mode for manual testing"""
    print("\n" + "="*60)
    print("INTERACTIVE MODE")
    print("="*60)
    
    client = SegmentationClient(user_id="interactive_user")
    
    if not await client.connect():
        return
    
    print("\nCommands:")
    print("  1 - Send full segmentation")
    print("  2 - Send delta (brush stroke)")
    print("  3 - Listen for 10 seconds")
    print("  q - Quit")
    
    current = create_empty_segmentation()
    
    while True:
        cmd = input("\nCommand: ").strip()
        
        if cmd == "1":
            array = create_test_segmentation()
            await client.send_full_segmentation(array)
            current = array
        
        elif cmd == "2":
            import random
            start = tuple(random.randint(5, d-5) for d in DIMENSIONS[::-1])
            end = tuple(s + random.randint(-5, 5) for s in start)
            
            new_array = paint_brush_stroke(current, start, end, radius=2, value=1)
            await client.send_delta(new_array)
            current = new_array
        
        elif cmd == "3":
            await client.receive_messages(duration=10)
        
        elif cmd == "q":
            break
        
        else:
            print("Unknown command")
    
    await client.disconnect()


# ============================================================================
# Main
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Test WebSocket Segmentation Client")
    parser.add_argument("--test", type=int, choices=[1, 2, 3, 4], 
                       help="Run specific test (1-4)")
    parser.add_argument("--interactive", action="store_true",
                       help="Run in interactive mode")
    parser.add_argument("--all", action="store_true",
                       help="Run all tests")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("WebSocket Segmentation Test Client")
    print("="*60)
    print(f"Server: {WS_URL}")
    print(f"Session: {SESSION_ID}")
    print(f"User: test_user")
    print(f"Dimensions: {DIMENSIONS}")
    print("="*60)
    
    try:
        if args.interactive:
            await interactive_mode()
        elif args.test == 1:
            await test_full_segmentation()
        elif args.test == 2:
            await test_delta_updates()
        elif args.test == 3:
            await test_two_clients()
        elif args.test == 4:
            await test_large_change()
        elif args.all:
            await test_full_segmentation()
            await asyncio.sleep(2)
            await test_delta_updates()
            await asyncio.sleep(2)
            await test_two_clients()
            await asyncio.sleep(2)
            await test_large_change()
        else:
            # Default: run all tests
            print("\nRunning all tests... (use --help for options)")
            await test_full_segmentation()
            await asyncio.sleep(2)
            await test_delta_updates()
            await asyncio.sleep(2)
            await test_two_clients()
            await asyncio.sleep(2)
            await test_large_change()
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("Tests complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
