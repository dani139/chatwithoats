# Build Stage
#sudo sqlite3 users.db "insert into users ('name','token') values ('admin','UsQSyX7KMf5QNSe1VMgZHqc6RZeXwqn1Tt0UuquKA')"
# ➜  whai git:(main) ✗ ssh -N -i ./bot_key.pem -L 8080:0.0.0.0:8080 ec2-user@ec2-51-17-101-231.il-central-1.compute.amazonaws.com
# visit: http://localhost:8080/login/?token=UsQSyX7KMf5QNSe1VMgZHqc6RZeXwqn1Tt0UuquKA

# after rebuild needed to visit this again, engouth for now, but will need to fix later.
#http://localhost:8080/login/?token=UsQSyX7KMf5QNSe1VMgZHqc6RZeXwqn1Tt0UuquKA


FROM golang:1.23-alpine AS build

# Install required packages
RUN apk add --no-cache gcc musl-dev curl git

# Set working directory
WORKDIR /app

# Clone the WuzAPI repository
RUN git clone https://github.com/asternic/wuzapi.git . && \
    go mod tidy && \
    CGO_ENABLED=1 go build -o server .

# Final Image
FROM alpine:latest

# Install runtime dependencies
RUN apk add --no-cache \
    curl \
    netcat-openbsd \
    iputils-ping \
    net-tools \
    sqlite

# Set working directory
WORKDIR /app

# Create and set permissions for required directories
RUN mkdir -p ssl dbdata && chmod -R 777 ssl dbdata

# Copy the compiled binary and static files from the build stage
COPY --from=build /app/server /app/
COPY --from=build /app/static /app/static

# Set environment variables
# ENV WUZAPI_ADMIN_TOKEN=UsQSyX7KMf5QNSe1VMgZHqc6RZeXwqn1Tt0UuquKA
# ENV WUZAPI_WEBHOOK_TIMEOUT=30
# ENV WUZAPI_MAX_RETRIES=3
# ENV WUZAPI_RETRY_DELAY=5

# Expose the API port
EXPOSE 8080

# Run the application
CMD ["/app/server", "-address", "0.0.0.0", "-logtype", "json"]
