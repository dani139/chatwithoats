-- Schema definition for the chatwithoats application

--
-- ENUM Types
--

CREATE TYPE public.httpmethod AS ENUM (
    'GET',
    'POST',
    'PUT',
    'DELETE',
    'PATCH'
);

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

CREATE TYPE public.sourcetype AS ENUM (
    'WHATSAPP',
    'PORTAL'
);

CREATE TYPE public.parameterplace AS ENUM (
    'QUERY',
    'HEADER',
    'PATH',
    'BODY'
);

--
-- Tables
--

CREATE TABLE public.apis (
    id character varying NOT NULL,
    server character varying NOT NULL,
    service character varying NOT NULL,
    provider character varying NOT NULL,
    version character varying NOT NULL,
    description character varying,
    processed boolean NOT NULL,
    keys jsonb,
    supported_paths jsonb,
    skip_parameters jsonb,
    keys_mapping jsonb,
    constant_parameters jsonb
);

CREATE TABLE public.api_requests (
    id character varying NOT NULL,
    api_id character varying NOT NULL,
    path character varying NOT NULL,
    method public.httpmethod NOT NULL,
    description character varying,
    keys jsonb,
    scopes jsonb,
    request_body jsonb,
    is_default_enabled boolean DEFAULT false NOT NULL,
    request_body_schema jsonb,
    response_schema jsonb,
    examples jsonb,
    summary text,
    skip_parameters jsonb,
    constant_parameters jsonb
);

CREATE TABLE public.api_parameters (
    id character varying NOT NULL,
    api_request_id character varying NOT NULL,
    name character varying NOT NULL,
    value jsonb,
    place public.parameterplace NOT NULL
);

CREATE TABLE public.portal_users (
    id character varying NOT NULL,
    email character varying NOT NULL,
    name character varying,
    password_hash character varying NOT NULL,
    is_verified boolean NOT NULL,
    verification_code character varying,
    verification_expiry timestamp without time zone,
    is_admin boolean DEFAULT false NOT NULL,
    linked_whatsapp_number character varying,
    default_chat_settings_id character varying,
    is_active boolean DEFAULT true NOT NULL,
    whatsapp_number character varying(255),
    last_login timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE public.chat_settings (
    id character varying NOT NULL,
    name character varying NOT NULL,
    description character varying,
    system_prompt character varying NOT NULL,
    is_default boolean NOT NULL,
    user_id character varying NOT NULL, -- Will be FK to portal_users.id
    model character varying DEFAULT 'gpt-4o-mini'::character varying,
    enabled_tools jsonb DEFAULT '[]'::jsonb NOT NULL
);

COMMENT ON COLUMN public.chat_settings.model IS 'OpenAI model to use for this chat setting, defaults to gpt-4o-mini';

CREATE TABLE public.conversations (
    chatid character varying NOT NULL,
    name character varying,
    is_group boolean NOT NULL,
    group_name character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    silent boolean NOT NULL,
    enabled_apis jsonb NOT NULL, -- Changed from json
    paths jsonb NOT NULL, -- Changed from json
    chat_settings_id character varying, -- Will be FK to chat_settings.id
    portal_user_id character varying(255), -- Will be FK to portal_users.id
    source_type public.sourcetype DEFAULT 'WHATSAPP'::public.sourcetype NOT NULL
);

CREATE TABLE public.conversation_participants (
    number character varying,
    chatid character varying -- Will be FK to conversations.chatid
);

CREATE TABLE public.messages (
    id character varying NOT NULL,
    chatid character varying NOT NULL, -- Will be FK to conversations.chatid
    sender character varying,
    sender_name character varying,
    type public.messagetype NOT NULL,
    content character varying,
    file_path character varying,
    caption character varying,
    latitude double precision,
    longitude double precision,
    quoted_message_id character varying, -- Self-referential FK to messages.id
    quoted_message_content character varying,
    role character varying,
    tool_call_id character varying,
    function_name character varying,
    function_arguments character varying, -- Consider jsonb if structured
    function_result character varying, -- Consider jsonb if structured
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE public.timers (
    id character varying NOT NULL,
    prompt character varying NOT NULL,
    date_time timestamp with time zone,
    repetition_interval integer, -- Consider renaming to repetition_interval_seconds or adding comment for unit
    chatid character varying NOT NULL -- Will be FK to conversations.chatid
);

CREATE TABLE public.user_scopes (
    id character varying NOT NULL,
    user_id character varying NOT NULL, -- Will be FK to portal_users.id
    api_id character varying NOT NULL, -- Will be FK to apis.id
    scope character varying NOT NULL
);

CREATE TABLE public.users ( -- This table seems to be a duplicate or legacy version of portal_users. Review if still needed.
    id character varying NOT NULL,
    email character varying NOT NULL,
    name character varying,
    password_hash character varying NOT NULL,
    is_verified boolean NOT NULL,
    verification_code character varying,
    verification_expiry timestamp without time zone,
    is_admin boolean DEFAULT false NOT NULL,
    linked_whatsapp_number character varying,
    default_chat_settings_id character varying, -- FK to chat_settings.id
    is_active boolean DEFAULT true NOT NULL
);

CREATE TABLE public.whatsapp_group_settings (
    id character varying NOT NULL,
    group_id character varying NOT NULL,
    chat_settings_id character varying NOT NULL, -- Will be FK to chat_settings.id
    enabled_tools jsonb DEFAULT '[]'::jsonb NOT NULL,
    system_prompt text,
    model character varying DEFAULT 'gpt-4o-mini'::character varying
);

--
-- Primary Keys
--

ALTER TABLE ONLY public.api_parameters
    ADD CONSTRAINT api_parameters_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.api_requests
    ADD CONSTRAINT api_requests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.apis
    ADD CONSTRAINT apis_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.chat_settings
    ADD CONSTRAINT chat_settings_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (chatid);

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.portal_users
    ADD CONSTRAINT portal_users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.timers
    ADD CONSTRAINT timers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_scopes
    ADD CONSTRAINT user_scopes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.whatsapp_group_settings
    ADD CONSTRAINT whatsapp_group_settings_pkey PRIMARY KEY (id);

--
-- Foreign Keys
--

ALTER TABLE ONLY public.api_requests
    ADD CONSTRAINT fk_api_requests_api_id FOREIGN KEY (api_id) REFERENCES public.apis(id);

ALTER TABLE ONLY public.api_parameters
    ADD CONSTRAINT fk_api_parameters_api_request_id FOREIGN KEY (api_request_id) REFERENCES public.api_requests(id);

ALTER TABLE ONLY public.chat_settings
    ADD CONSTRAINT fk_chat_settings_user_id FOREIGN KEY (user_id) REFERENCES public.portal_users(id);

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT fk_conversations_chat_settings_id FOREIGN KEY (chat_settings_id) REFERENCES public.chat_settings(id);

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT fk_conversations_portal_user_id FOREIGN KEY (portal_user_id) REFERENCES public.portal_users(id);

ALTER TABLE ONLY public.conversation_participants
    ADD CONSTRAINT fk_conversation_participants_chatid FOREIGN KEY (chatid) REFERENCES public.conversations(chatid);

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_chatid FOREIGN KEY (chatid) REFERENCES public.conversations(chatid);

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_quoted_message_id FOREIGN KEY (quoted_message_id) REFERENCES public.messages(id);

ALTER TABLE ONLY public.portal_users
    ADD CONSTRAINT fk_portal_users_default_chat_settings_id FOREIGN KEY (default_chat_settings_id) REFERENCES public.chat_settings(id);

ALTER TABLE ONLY public.timers
    ADD CONSTRAINT fk_timers_chatid FOREIGN KEY (chatid) REFERENCES public.conversations(chatid);

ALTER TABLE ONLY public.user_scopes
    ADD CONSTRAINT fk_user_scopes_api_id FOREIGN KEY (api_id) REFERENCES public.apis(id);

ALTER TABLE ONLY public.user_scopes
    ADD CONSTRAINT fk_user_scopes_user_id FOREIGN KEY (user_id) REFERENCES public.portal_users(id);

-- Assuming users.default_chat_settings_id references chat_settings.id
ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_default_chat_settings_id FOREIGN KEY (default_chat_settings_id) REFERENCES public.chat_settings(id);

ALTER TABLE ONLY public.whatsapp_group_settings
    ADD CONSTRAINT fk_whatsapp_group_settings_chat_settings_id FOREIGN KEY (chat_settings_id) REFERENCES public.chat_settings(id);

--
-- Indexes (besides PKs and some unique indexes already present)
-- Note: FKs often benefit from indexes on the referencing column(s).
--

-- Existing indexes (retained from original script, check if all are still optimal)
CREATE INDEX idx_chat_settings_model ON public.chat_settings USING btree (model);
CREATE INDEX idx_conversations_portal_user_id ON public.conversations USING btree (portal_user_id); -- Covered by FK now, but specific index might have different characteristics
CREATE UNIQUE INDEX ix_portal_users_email ON public.portal_users USING btree (email);
CREATE INDEX ix_whatsapp_group_settings_group_id ON public.whatsapp_group_settings USING btree (group_id);

-- New indexes for foreign keys (if not already primary key of the referencing table)
CREATE INDEX idx_api_requests_api_id ON public.api_requests(api_id);
CREATE INDEX idx_api_parameters_api_request_id ON public.api_parameters(api_request_id);
CREATE INDEX idx_chat_settings_user_id ON public.chat_settings(user_id);
CREATE INDEX idx_conversations_chat_settings_id ON public.conversations(chat_settings_id);
-- idx_conversations_portal_user_id already exists
CREATE INDEX idx_conversation_participants_chatid ON public.conversation_participants(chatid);
CREATE INDEX idx_messages_chatid ON public.messages(chatid);
CREATE INDEX idx_messages_quoted_message_id ON public.messages(quoted_message_id);
CREATE INDEX idx_portal_users_default_chat_settings_id ON public.portal_users(default_chat_settings_id);
CREATE INDEX idx_timers_chatid ON public.timers(chatid);
CREATE INDEX idx_user_scopes_api_id ON public.user_scopes(api_id);
CREATE INDEX idx_user_scopes_user_id ON public.user_scopes(user_id);
CREATE INDEX idx_users_default_chat_settings_id ON public.users(default_chat_settings_id);
CREATE INDEX idx_whatsapp_group_settings_chat_settings_id ON public.whatsapp_group_settings(chat_settings_id);

-- Comments from original script (retained)
-- COMMENT ON COLUMN public.chat_settings.model IS 'OpenAI model to use for this chat setting, defaults to gpt-4o-mini';
-- Note: Some ALTER TABLE ... OWNER TO admin; lines and comments were removed for brevity and because ownership is typically handled by the executing user.
-- The table public.users seems very similar to public.portal_users. Review if it's a duplicate or serves a distinct purpose.

-- End of cleaned schema

