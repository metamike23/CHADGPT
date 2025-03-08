from json import loads, dumps
from datetime import datetime
from flask import request
import requests
import os
import itertools  # Used for round-robin cycling
import re

from server.config import special_instructions  # Restored jailbreak handling

class Backend_Api:
    def __init__(self, app, config: dict) -> None:
        self.app = app

        # List of LlamaCPP servers for load balancing
        self.llama_servers = [
            "http://belto.myftp.biz:9999/v1/chat/completions",
            "http://localhost:8080/v1/chat/completions"
        ]

        # Create a round-robin cycle iterator
        self.server_cycle = itertools.cycle(self.llama_servers)

        self.routes = {
            '/backend-api/v2/conversation': {
                'function': self._conversation,
                'methods': ['POST']
            }
        }

    def _conversation(self):
        try:
            # Extract request parameters
            jailbreak = request.json.get('jailbreak', 'default')
            _conversation = request.json['meta']['content']['conversation']
            prompt = request.json['meta']['content']['parts'][0]
            current_date = datetime.now().strftime("%Y-%m-%d")
            internet_access = request.json['meta']['content']['internet_access']

            if internet_access:
                internet_query = prompt["content"]
                print(f"Internet Access Query: {internet_query}")
                



            # Construct system message with current date
            system_message = {
                "role": "system",
                "content": f'You are BeltoAI, a large language model implemented by experts with Belto. Strictly follow the users instructions. Current date: {current_date}'
            }

            # Construct conversation with jailbreak instructions
            conversation = [system_message] + special_instructions.get(jailbreak, []) + _conversation + [prompt]

            # Select the next LlamaCPP server using round-robin
            selected_server = next(self.server_cycle)
            print(selected_server)

            # Prepare the request payload
            payload = {
                "model": request.json.get("model", "gpt-3.5-turbo"),  # Default model
                "messages": conversation,
                "stream": True  # Streaming enabled for continuous response
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer <API-KEY>"  # Shared API key
            }

            # Send request to the selected LlamaCPP server
            print(f"Sending request to LlamaCPP server: {selected_server}")
            print(f"Payload: {dumps(payload, indent=2)}")

            llama_resp = requests.post(selected_server, headers=headers, json=payload, stream=True)

            # Log status code for debugging
            print(f"Response Status Code: {llama_resp.status_code}")

            if llama_resp.status_code >= 400:
                print(f"Error Response: {llama_resp.text}")
                return {
                    "success": False,
                    "error_code": llama_resp.status_code,
                    "message": llama_resp.text
                }, llama_resp.status_code

            # Streaming the response back to the client
            def stream():
                for chunk in llama_resp.iter_lines():
                    if not chunk:
                        continue  # Skip empty lines

                    decoded_chunk = chunk.decode("utf-8").strip()

                    # Ignore "[DONE]" signal
                    if decoded_chunk == "data: [DONE]":
                        break

                    # Ensure we only parse valid JSON chunks
                    if decoded_chunk.startswith("data: "):
                        try:
                            json_data = loads(decoded_chunk[6:])  # Remove "data: " prefix
                            token = json_data["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except Exception as e:
                            print(f"Error parsing chunk: {e}")
                            continue  # Skip invalid chunks

            return self.app.response_class(stream(), mimetype="text/event-stream")

        except Exception as e:
            print(f"Exception: {e}")
            return {
                "success": False,
                "error": f"An error occurred: {str(e)}"
            }, 400






