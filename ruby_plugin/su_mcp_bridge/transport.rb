require 'socket'
require 'digest/sha1'
require 'base64'

module SUMCPBridge
  class WSTransport
    WS_MAGIC_STRING = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def initialize(start_port = 9876)
      @port = start_port
      begin
        @server = TCPServer.new('127.0.0.1', @port)
      rescue StandardError => e
        puts "SUMCPBridge: port #{@port} failed (#{e.message}), trying next..."
        @port += 1
        retry if @port < start_port + 10
        raise "Could not find an available port for SUMCPBridge (tried #{start_port}..#{start_port+9})"
      end
      @client = nil
      puts "SUMCPBridge: WebSocket server listening on port #{@port}"
      
      begin
        port_file = File.join(ENV['USERPROFILE'] || ENV['HOME'], '.su_mcp_port')
        File.write(port_file, @port.to_s)
      rescue => e
        puts "SUMCPBridge: Could not write port file: #{e.message}"
      end
    end
    
    attr_reader :port

    # Non-blocking poll for new connections or messages
    def poll(&block)
      # Accept new client if none
      if @client.nil?
        begin
          socket = @server.accept_nonblock
          if handshake(socket)
            @client = socket
            puts "SUMCPBridge: Client connected via WebSocket"
          else
            socket.close
          end
        rescue IO::WaitReadable, Errno::EINTR
          # No new connection
        rescue => e
          puts "SUMCPBridge: Error accepting connection: #{e.message}"
        end
      end

      # Read from client if exists
      if @client
        begin
          # Check if data is ready
          rs, _, _ = IO.select([@client], nil, nil, 0)
          if rs && rs.any?
            msg = read_frame(@client)
            if msg
              block.call(msg, self) if block_given?
            else
              # Client disconnected
              @client.close
              @client = nil
              puts "SUMCPBridge: Client disconnected"
            end
          end
        rescue IO::WaitReadable
          # Normal
        rescue => e
          puts "SUMCPBridge: Client error: #{e.message}"
          @client.close if @client
          @client = nil
        end
      end
    end

    def send_message(msg)
      return unless @client
      begin
        frame = create_frame(msg)
        @client.write(frame)
      rescue => e
        puts "SUMCPBridge: Send error: #{e.message}"
        @client.close
        @client = nil
      end
    end

    private

    def handshake(socket)
      headers = {}
      while line = socket.gets
        line = line.strip
        break if line.empty?
        if line.match(/^([^:]+):\s*(.+)$/)
          headers[$1] = $2
        end
      end

      return false unless headers['Sec-WebSocket-Key']

      accept_key = Base64.strict_encode64(Digest::SHA1.digest(headers['Sec-WebSocket-Key'] + WS_MAGIC_STRING))
      
      response = "HTTP/1.1 101 Switching Protocols\r\n" +
                 "Upgrade: websocket\r\n" +
                 "Connection: Upgrade\r\n" +
                 "Sec-WebSocket-Accept: #{accept_key}\r\n\r\n"
      
      socket.write(response)
      true
    end

    def read_frame(socket)
      first_byte = socket.read(1)
      return nil unless first_byte
      
      first_byte = first_byte.unpack1("C")
      fin = (first_byte & 0b10000000) != 0
      opcode = first_byte & 0b00001111
      
      # Close connection opcode
      return nil if opcode == 8

      second_byte = socket.read(1).unpack1("C")
      masked = (second_byte & 0b10000000) != 0
      payload_len = second_byte & 0b01111111

      if payload_len == 126
        payload_len = socket.read(2).unpack1("n")
      elsif payload_len == 127
        payload_len = socket.read(8).unpack1("Q>")
      end

      masking_key = socket.read(4).bytes if masked
      payload_data = socket.read(payload_len)
      
      return nil unless payload_data

      if masked
        unmasked_data = payload_data.bytes.each_with_index.map do |byte, i|
          byte ^ masking_key[i % 4]
        end.pack("C*")
        return unmasked_data.force_encoding("UTF-8")
      else
        return payload_data.force_encoding("UTF-8")
      end
    end

    def create_frame(msg)
      payload = msg.b
      length = payload.bytesize

      frame = "".b
      frame << 0b10000001.chr # FIN and Text opcode

      if length <= 125
        frame << length.chr
      elsif length <= 65535
        frame << 126.chr
        frame << [length].pack("n")
      else
        frame << 127.chr
        frame << [length].pack("Q>")
      end

      frame << payload
      frame
    end
  end
end
