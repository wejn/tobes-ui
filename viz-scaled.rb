#!/usr/bin/env ruby

# Re-scales multiple *.json files and visualizes them with tobes-ui
# 
# Example:
# $ ruby viz-scaled.rb -m \
#   hpcs-320=OHS-194803.json \
#   flame-s-vis-nir-es=flame.json \
#   torchbearer=spectrum-1753872012.821302.json

require 'optparse'
require 'tempfile'
require 'json'

options = {
    wavelength: nil,
    max: true,
    rename: false,
    cmd: %w[python3 main.py -t overlay -d],
}

OptionParser.new do |opts|
    opts.banner = "Usage: #{File.basename($0)} [options]"

    opts.on("-wWL", "--wavelength=WL", Integer, "Align on wavelength") do |wl|
        options[:max] = false
        options[:wavelength] = wl
    end

    opts.on("-m", "--[no-]max", "Align on max value (default)") do |max|
        options[:max] = max
    end

    opts.on("-n", "--[no-]name-by-file", "Name by file") do |name|
        options[:rename] = name
    end

    opts.on('-c', '--command=CMD', "Tobes-ui command, default: #{options[:cmd]}") do |cmd|
        options[:command] = cmd
    end
end.parse!

if options[:wavelength] && options[:max]
    STDERR.puts "Can't have both -w and -m"
    exit 1
end

if ARGV.size.zero?
    STDERR.puts "Need at least one input JSON file"
end

Entries = Struct.new(:file, :wl, :max, :val_at_wl, :name, :data)

entries = []

for file in ARGV
    begin
        name = nil
        if !FileTest.exist?(file) && file =~ /(.*?)=(.*)/ && FileTest.exist?($2)
            name = $1
            file = $2
        end
        data = JSON.parse(File.read(file))
        entries << Entries.new(
            name || file,
            Range.new(*data["wavelength_range"]),
            data["spd"].map { |k,v| v }.max,
            data["spd"][options[:wavelength].to_s],
            data["name"],
            data
        )
    rescue JSON::ParserError
        STDERR.puts "Can't parse #{file}: json parse error"
    rescue
        STDERR.puts "Can't parse #{file}: #{$!}"
    end
end

scaler = 
    if options[:max]
        # rescale to max
        entries.map(&:max).max
    elsif options[:wavelength]
        non_conforming = entries.find_all { |x| x.val_at_wl.nil? }
        unless non_conforming.empty?
            STDERR.puts "Can't align on #{options[:wavelength]} because these files don't contain it:"
            STDERR.puts non_conforming.map(&:file).join(', ')
            exit 1
        end

        # rescale to val_at_wl
        entries.map(&:val_at_wl).max
    else
        1.0
    end

entries.each do |e|
    e.data["spd"] = e.data['spd'].map { |k,v| [k, v * (scaler / e.max)] }.to_h
    e.data.delete('wavelengths_raw')
    e.data.delete('spd_raw')
    e.data["axis"] = 'counts'
    e.data["name"] = e.file.gsub(/(.*\/)?(.*)(\..*$)/, '\\2') if options[:rename]
end

tempfiles = entries.map do |e|
    tf = Tempfile.new('viz-scaled')
    tf.write(e.data.to_json)
    tf.flush
    tf

end

if options[:cmd].kind_of?(String)
    system(options[:cmd] + ' ' + tempfiles.map(&:path).join(' '))
else
    system(*(options[:cmd] + tempfiles.map(&:path)))
end
