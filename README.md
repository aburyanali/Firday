<div align="center">

# Friday
### Your Intelligent AI Operating System

*A modular AI runtime that combines cloud LLMs, local models, real-time system awareness, intelligent routing, memory, and project understanding into one unified assistant.*

> **⚠️ Active Development:** Friday is currently under active development. New capabilities, architectural improvements, and experimental features are being added continuously.

---

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991)
![Ollama](https://img.shields.io/badge/Ollama-Local%20LLMs-black)
![WebSocket](https://img.shields.io/badge/WebSockets-Streaming-success)
![Status](https://img.shields.io/badge/Status-Active%20Development-orange)

</div>

---

# Vision

Friday is more than another chatbot.

The goal of this project is to build an **AI Operating System** capable of reasoning, remembering, adapting, monitoring its environment, and intelligently selecting the best AI model for every task.

Instead of depending on a single LLM, Friday acts as an orchestration layer that combines multiple intelligence providers into one seamless experience.

The long-term vision is to create an assistant that feels less like a chatbot and more like a true digital operating companion.

---

# Why Friday?

Most AI assistants simply forward prompts to a single language model.

Friday introduces an intelligent runtime capable of:

- Multi-provider AI routing
- Automatic failover
- Project-aware reasoning
- Long-term memory
- Real-time hardware awareness
- Streaming conversations
- Local + cloud intelligence
- Modular backend architecture

---

# Core Features

## Multi-Provider Intelligence

Friday intelligently routes requests between multiple AI providers depending on complexity, latency, and availability.

Current providers include:

- OpenAI
- Ollama
- Perplexity
- Local Offline Fallback Engine

If one provider becomes unavailable, another provider automatically takes over.

---

## Intelligent Reasoning Engine

Every request goes through an internal reasoning pipeline before reaching any model.

The reasoning system performs:

- Objective understanding
- Intent classification
- Task profiling
- Context building
- Memory retrieval
- Project understanding
- System prompt generation

This enables more consistent and context-aware responses.

---

## Project Intelligence

Friday can understand its own codebase.

When discussing the project itself, the backend automatically searches relevant project files and injects them into the AI context, allowing discussions grounded in the actual implementation rather than assumptions.

---

## Memory System

Friday remembers important long-term information such as:

- User preferences
- Goals
- Project information
- Conversation history

This enables increasingly personalized interactions over time.

---

## Real-Time System Awareness

Friday can observe the machine it is running on.

Examples include:

- CPU usage
- RAM utilization
- Battery status
- Running processes
- Network connectivity
- Time
- Weather (experimental)

This allows contextual responses based on the current environment.

---

## Streaming Runtime

Responses are streamed token-by-token using WebSockets for a responsive conversational experience.

Features include:

- Real-time streaming
- Interrupt support
- Session management
- Background task tracking
- Runtime state transitions

---

## Verification Engine

Before responses are returned, Friday performs automatic quality checks including:

- Response completeness
- Missing code detection
- Explanation verification
- Architecture validation
- Debugging quality

---

# System Architecture

```
                   User
                     │
                     ▼
             FastAPI Backend
                     │
                     ▼
          Reasoning Engine
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   Memory      Project AI    Task Profile
        │            │            │
        └────────────┼────────────┘
                     ▼
             Provider Router
        ┌─────────┬──────────┬──────────┐
        ▼         ▼          ▼          ▼
     OpenAI    Ollama   Perplexity   Local AI
        └─────────┬──────────┬─────────┘
                  ▼
          Verification Engine
                  ▼
          Streaming Response
                  ▼
               Frontend
```

---

# Backend Structure

```
nova_backend/

├── intelligence/
│   ├── reasoning_engine.py
│   ├── memory_intelligence.py
│   ├── request_classifier.py
│   ├── project_intelligence.py
│   └── verification_engine.py
│
├── providers/
│   ├── provider_router.py
│   ├── provider_manager.py
│   ├── openai_provider.py
│   ├── ollama_provider.py
│   ├── perplexity_provider.py
│   └── fallback_engine.py
│
├── runtime/
│   ├── state.py
│   ├── sessions.py
│   ├── events.py
│   └── telemetry.py
│
└── services/
```

---

# Tech Stack

### Backend

- Python
- FastAPI
- WebSockets
- Pydantic

### AI

- OpenAI
- Ollama
- Perplexity AI

### Intelligence

- Custom Reasoning Engine
- Memory Intelligence
- Project Intelligence
- Verification Engine

### Frontend

- Next.js
- React
- TypeScript

---

# Current Capabilities

- Intelligent Provider Routing
- Automatic Provider Failover
- Streaming Responses
- Project-Aware AI
- Memory System
- Voice Processing
- Runtime State Machine
- Real-Time Telemetry
- Symbolic Mathematics
- Session Management
- Intelligent Prompt Construction
- Response Verification

---

# Roadmap

### Phase 1

- Backend Runtime
- Provider Routing
- Memory System
- Streaming Architecture

### Phase 2

- Voice Interaction
- Project Intelligence
- Verification Engine

### Phase 3

- Desktop Client
- Plugin System
- Persistent Memory
- Vision Support
- Multi-Agent Collaboration
- Local Knowledge Base
- Autonomous Workflows

---

# Project Status

This project is actively evolving.

Current priorities include:

- Improving reasoning capabilities
- Persistent memory
- Better provider selection
- Vision support
- Performance optimization
- Desktop integration
- Autonomous agent workflows

---

# Contributing

Contributions, discussions, feature suggestions, and architecture ideas are always welcome.

If you're interested in AI systems engineering, backend architecture, or intelligent runtime design, feel free to open an issue or submit a pull request.

---

# Disclaimer

Friday is an experimental AI operating system built for research, learning, and exploration of intelligent runtime architectures.

Some features are experimental and may change significantly as development continues.

---

<div align="center">

### Built with curiosity, countless late nights, and a vision for the future of intelligent systems.

⭐ If you like this project, consider giving it a star.

</div>
