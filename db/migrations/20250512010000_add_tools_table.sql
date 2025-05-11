-- Add tools table and chat_settings_tools association table

-- Create tools table
CREATE TABLE IF NOT EXISTS public.tools (
    id character varying NOT NULL,
    name character varying NOT NULL,
    description character varying,
    type character varying NOT NULL,
    configuration jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    PRIMARY KEY (id)
);

-- Create chat_settings_tools association table
CREATE TABLE IF NOT EXISTS public.chat_settings_tools (
    chat_settings_id character varying NOT NULL,
    tool_id character varying NOT NULL,
    CONSTRAINT fk_chat_settings_id FOREIGN KEY (chat_settings_id) REFERENCES public.chat_settings(id),
    CONSTRAINT fk_tool_id FOREIGN KEY (tool_id) REFERENCES public.tools(id),
    PRIMARY KEY (chat_settings_id, tool_id)
);

-- Create indexes for better query performance
CREATE INDEX idx_tools_type ON public.tools(type);
CREATE INDEX idx_chat_settings_tools_chat_settings_id ON public.chat_settings_tools(chat_settings_id);
CREATE INDEX idx_chat_settings_tools_tool_id ON public.chat_settings_tools(tool_id); 