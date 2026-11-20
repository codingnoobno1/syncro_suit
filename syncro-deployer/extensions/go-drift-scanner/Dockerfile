FROM golang:1.22-alpine AS builder
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /go-drift-scanner .

FROM scratch
COPY --from=builder /go-drift-scanner /go-drift-scanner
USER 10001:10001
EXPOSE 9101
ENTRYPOINT ["/go-drift-scanner"]
