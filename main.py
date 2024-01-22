from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
import uvicorn
import subprocess
import shlex

app = FastAPI()


class InteractiveConsole:
    def __init__(self):
        self.stdin = subprocess.PIPE
        self.persistent_process = subprocess.Popen(
            ["echo", "Welcome to STORM CLI"],
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=self.stdin,
        )

    async def run_command(self, command: str, websocket: WebSocket):
        try:
            if (not self.persistent_process) or self.persistent_process.poll():
                self.persistent_process = subprocess.Popen(
                    shlex.split(command),
                    shell=True,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=self.stdin,
                )
                result, error = self.persistent_process.communicate()
            else:
                try:
                    result, error = self.persistent_process.communicate(input=command)
                except Exception as e:
                    print(e)
                    self.persistent_process = None
                    await self.run_command(command, websocket)
                    return
            if result:
                await websocket.send_text(result)
            if error:
                await websocket.send_text(f"Error: {error}")
        except Exception as e:
            await websocket.send_text(f"Error: {str(e)}")

    async def close_session(self):
        if self.persistent_process:
            self.persistent_process.terminate()
            self.persistent_process = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    interactive_console = InteractiveConsole()

    await interactive_console.run_command("", websocket)

    try:
        while True:
            command = await websocket.receive_text()

            if command.lower() == "exit":
                await websocket.send_text("Exiting session.")
                await interactive_console.close_session()
                await websocket.close(1000)
                break

            await interactive_console.run_command(command, websocket)

    except WebSocketDisconnect:
        await interactive_console.close_session()


@app.get("/run")
async def run_command(command: str):
    try:
        result = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT)
        return {"result": result}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Error: {e.output}")


@app.get("/console", response_class=HTMLResponse)
async def console_ui(request: Request):
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Console</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            margin: 20px;
        }
        #output {
            white-space: pre-line;
        }
    </style>
</head>
<body>
    <h2>Interactive Console</h2>
    <textarea id="output" rows="10" cols="80" readonly></textarea>
    <br>
    <input type="text" id="input" placeholder="Enter CLI command">
    <button onclick="sendCommand()">Send</button>

    <script>
        const socket = new WebSocket("wss://%s/ws");

        socket.onmessage = function(event) {
            const outputElement = document.getElementById("output");
            outputElement.value += event.data + "\\n";
        };

        function sendCommand() {
            const inputElement = document.getElementById("input");
            const command = inputElement.value;
            socket.send(command);
            inputElement.value = "";
        }
    </script>
</body>
</html>
""" % request.url.netloc
    return HTMLResponse(content=html_content, status_code=200)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5335)
