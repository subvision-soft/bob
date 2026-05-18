<center><img src="Bob.png"></center>

# BOB (Broadcast Operator Bot)

BOB is an automation system that controls OBS scene switching in real time based on live event detection.

## Overview

Broadcast Operator Bot (BOB) automatically changes scenes in OBS by reacting to detected events during a live broadcast.  
It is designed to reduce manual camera switching and improve production responsiveness.

Typical use cases include:
- Sports competitions (e.g. competitor shoots, finish line crossing)
- Real-time event coverage
- Automated multi-camera productions

## How it works

BOB listens to live event inputs (from AI models, sensors, or external APIs) and maps them to OBS scene transitions.

Example events:
- A competitor makes a shot → switch to close-up camera
- Competitors crosses finish line → switch to finish line camera
- Start of race → switch to wide overview

## Features

- Real-time scene switching in OBS
- Event-driven architecture
- Extensible event input system
- Designed for live sports and automated broadcasting

## Goal

Reduce manual intervention in live production and improve broadcast quality through intelligent automation.

## Tech (planned / example)

- OBS WebSocket API
- Python / FastAPI backend
- Computer vision / event detection system

## Status

Work in progress
