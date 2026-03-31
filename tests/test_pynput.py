import asyncio
from pynput import keyboard
import time

async def on_press_async(key):
    print(f"Async Press: {key}")

async def on_release_async(key):
    print(f"Async Release: {key}")
    if key == keyboard.Key.esc:
        print("Exiting...")
        asyncio.get_running_loop().stop()

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _on_press(k):
        print(f"Raw press: {k}")
        loop.call_soon_threadsafe(asyncio.ensure_future, on_press_async(k))
    
    def _on_release(k):
        print(f"Raw release: {k}")
        loop.call_soon_threadsafe(asyncio.ensure_future, on_release_async(k))

    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()

    print("Listener started.")
    
    # Simulate a keypress in a separate thread
    import threading
    def simulate():
        time.sleep(1)
        print("Simulating F2 press...")
        ctrl = keyboard.Controller()
        ctrl.press(keyboard.Key.f2)
        time.sleep(1)
        ctrl.release(keyboard.Key.f2)
        time.sleep(1)
        ctrl.press(keyboard.Key.esc)
        ctrl.release(keyboard.Key.esc)
        
    threading.Thread(target=simulate, daemon=True).start()

    try:
        loop.run_forever()
    finally:
        loop.close()

if __name__ == "__main__":
    main()
