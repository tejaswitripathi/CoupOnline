export function connectGameSocket(gameId: string, onMessage: (payload: unknown) => void) {
  const wsRoot = import.meta.env.VITE_WS_ROOT ?? "ws://127.0.0.1:8000/ws";
  const socket = new WebSocket(`${wsRoot}/games/${gameId}`);

  socket.addEventListener("message", (event) => {
    onMessage(JSON.parse(event.data));
  });

  return socket;
}
