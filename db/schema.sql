-- ChatWithOats Database Schema
-- This file defines the SQL schema for the ChatWithOats application.

--
-- ENUM Types
--

-- Message types
CREATE TYPE public.messagetype AS ENUM (
    'TEXT',
    'VOICE',
    'IMAGE',
    'MEDIA',
    'LOCATION',
    'SYSTEM',
    'TOOL_CALL',
    'TOOL_RESULT'
);

-- Source types
CREATE TYPE public.sourcetype AS ENUM (
    'WHATSAPP',
    'PORTAL'
);

--
-- Tables
--

-- Portal users table
CREATE TABLE public.portal_users (
    id character varying NOT NULL PRIMARY KEY,
    username character varying NOT NULL,
    email character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);

-- APIs table
CREATE TABLE public.apis (
    id character varying NOT NULL PRIMARY KEY,
    server character varying NOT NULL,
    service character varying NOT NULL,
    provider character varying NOT NULL,
    version character varying NOT NULL,
    description character varying,
    processed boolean NOT NULL
);

-- API requests table
CREATE TABLE public.api_requests (
    id character varying NOT NULL PRIMARY KEY,
    api_id character varying NOT NULL REFERENCES public.apis(id),
    path character varying NOT NULL,
    method character varying NOT NULL,
    description character varying,
    request_body_schema jsonb,
    response_schema jsonb,
    skip_parameters jsonb,
    constant_parameters jsonb
);

-- Chat settings table
CREATE TABLE public.chat_settings (
    id character varying NOT NULL PRIMARY KEY,
    name character varying NOT NULL,
    description character varying,
    system_prompt character varying NOT NULL,
    model character varying NOT NULL DEFAULT 'gpt-4o-mini'
);

-- Tools table
CREATE TABLE public.tools (
    id character varying NOT NULL PRIMARY KEY,
    name character varying,
    description character varying,
    type character varying NOT NULL,
    tool_type character varying,
    api_request_id character varying REFERENCES public.api_requests(id),
    configuration jsonb NOT NULL,
    function_schema jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);

-- Chat settings to tools many-to-many relationship
CREATE TABLE public.chat_settings_tools (
    chat_settings_id character varying NOT NULL REFERENCES public.chat_settings(id),
    tool_id character varying NOT NULL REFERENCES public.tools(id),
    PRIMARY KEY (chat_settings_id, tool_id)
);

-- Conversations table
CREATE TABLE public.conversations (
    chatid character varying NOT NULL PRIMARY KEY,
    name character varying,
    is_group boolean NOT NULL,
    group_name character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    silent boolean NOT NULL,
    enabled_apis jsonb NOT NULL,
    paths jsonb NOT NULL,
    chat_settings_id character varying REFERENCES public.chat_settings(id),
    portal_user_id character varying REFERENCES public.portal_users(id),
    source_type public.sourcetype DEFAULT 'WHATSAPP'::public.sourcetype NOT NULL
);

-- Conversation participants table
CREATE TABLE public.conversation_participants (
    number character varying NOT NULL,
    chatid character varying NOT NULL REFERENCES public.conversations(chatid),
    PRIMARY KEY (number, chatid)
);

-- Messages table
CREATE TABLE public.messages (
    id character varying NOT NULL PRIMARY KEY,
    chatid character varying NOT NULL REFERENCES public.conversations(chatid),
    sender character varying,
    sender_name character varying,
    type public.messagetype NOT NULL,
    content character varying,
    file_path character varying,
    caption character varying,
    latitude double precision,
    longitude double precision,
    quoted_message_id character varying REFERENCES public.messages(id),
    quoted_message_content character varying,
    role character varying,
    openai_tool_call_id character varying,
    tool_call_id character varying,
    tool_definition_name character varying,
    openai_function_name character varying,
    function_arguments character varying,
    function_result character varying,
    created_at timestamp with time zone DEFAULT now()
);

--
-- Indexes
--

-- Indexes for portal_users table
CREATE INDEX idx_portal_users_email ON public.portal_users(email);

-- Indexes for apis table
CREATE INDEX idx_apis_provider ON public.apis(provider);
CREATE INDEX idx_apis_service ON public.apis(service);

-- Indexes for api_requests table
CREATE INDEX idx_api_requests_api_id ON public.api_requests(api_id);
CREATE INDEX idx_api_requests_method ON public.api_requests(method);

-- Indexes for chat_settings table
CREATE INDEX idx_chat_settings_model ON public.chat_settings(model);

-- Indexes for tools table
CREATE INDEX idx_tools_type ON public.tools(type);
CREATE INDEX idx_tools_tool_type ON public.tools(tool_type);
CREATE INDEX idx_tools_api_request_id ON public.tools(api_request_id);

-- Indexes for chat_settings_tools table
CREATE INDEX idx_chat_settings_tools_chat_settings_id ON public.chat_settings_tools(chat_settings_id);
CREATE INDEX idx_chat_settings_tools_tool_id ON public.chat_settings_tools(tool_id);

-- Indexes for conversations table
CREATE INDEX idx_conversations_chat_settings_id ON public.conversations(chat_settings_id);
CREATE INDEX idx_conversations_portal_user_id ON public.conversations(portal_user_id);
CREATE INDEX idx_conversations_source_type ON public.conversations(source_type);

-- Indexes for conversation_participants table
CREATE INDEX idx_conversation_participants_chatid ON public.conversation_participants(chatid);

-- Indexes for messages table
CREATE INDEX idx_messages_chatid ON public.messages(chatid);
CREATE INDEX idx_messages_type ON public.messages(type);
CREATE INDEX idx_messages_quoted_message_id ON public.messages(quoted_message_id);
CREATE INDEX idx_messages_created_at ON public.messages(created_at);
CREATE INDEX idx_messages_tool_call_id ON public.messages(tool_call_id); 