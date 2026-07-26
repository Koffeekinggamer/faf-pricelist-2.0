#!/usr/bin/env ruby
# Analyze builder Excel pricelist layouts (stdlib + unzip only)
require "rexml/document"
require "tmpdir"
require "json"

def col_letters(ref)
  ref.to_s[/^[A-Z]+/]
end

def alphaish?(c)
  c =~ /[A-Za-z]/ && c !~ /^\$?[\d,\.]+$/
end

def analyze(path)
  out = { "file" => File.basename(path), "path" => path, "sheets" => [], "error" => nil }
  Dir.mktmpdir("xlsx") do |dir|
    ok = system("unzip", "-qq", "-o", path, "-d", dir)
    return out.merge("error" => "unzip failed") unless ok

    wb_path = File.join(dir, "xl/workbook.xml")
    return out.merge("error" => "no workbook") unless File.exist?(wb_path)

    wb = REXML::Document.new(File.read(wb_path))
    sheets = []
    wb.elements.each("//sheet") { |s| sheets << s.attributes["name"] }

    ss = []
    ss_path = File.join(dir, "xl/sharedStrings.xml")
    if File.exist?(ss_path)
      sdoc = REXML::Document.new(File.read(ss_path))
      sdoc.elements.each("sst/si") do |si|
        texts = []
        si.elements.each(".//t") { |t| texts << t.text.to_s }
        ss << texts.join
      end
    end

    sheets.first(6).each_with_index do |name, idx|
      sp = File.join(dir, "xl/worksheets/sheet#{idx + 1}.xml")
      next unless File.exist?(sp)

      # Large sheets: stream roughly via regex for first N rows if REXML is heavy
      xml = File.read(sp)
      dim_m = xml.match(/<dimension[^>]*ref="([^"]+)"/)
      ref = dim_m ? dim_m[1] : nil

      row_data = []
      # Parse with REXML only first chunk if huge
      begin
        sdoc = REXML::Document.new(xml)
      rescue
        # truncate attempt
        partial = xml[0, 2_000_000]
        partial += "</sheetData></worksheet>" unless partial.include?("</worksheet>")
        sdoc = REXML::Document.new(partial) rescue nil
        next unless sdoc
      end

      sdoc.elements.each("worksheet/sheetData/row") do |row|
        ridx = row.attributes["r"].to_i
        break if ridx > 35
        cells = {}
        row.elements.each("c") do |c|
          cref = c.attributes["r"]
          col = col_letters(cref)
          t = c.attributes["t"]
          v_el = c.elements["v"]
          val = v_el ? v_el.text.to_s : ""
          if t == "s"
            val = ss[val.to_i] rescue val
          elsif t == "inlineStr"
            val = ""
            c.elements.each("is//t") { |tnode| val << tnode.text.to_s }
          end
          cells[col] = val.strip
        end
        ordered = cells.sort_by { |k, _| [k.length, k] }.map { |_, v| v }.reject(&:empty?)
        row_data << { "r" => ridx, "cells" => ordered.first(20), "n" => cells.size }
      end

      candidates = row_data.select { |r| r["r"] <= 18 && r["n"] >= 2 }
      header = candidates.max_by do |r|
        r["cells"].count { |c| alphaish?(c) }
      end

      hdr = header ? header["cells"] : []
      hdr_join = hdr.join(" | ").downcase

      species_hits = hdr.count { |h| h =~ /maple|oak|cherry|walnut|hickory|elm|pine|birch|qswo|pswo|wormy|ash|poplar|species/i }
      price_hits = hdr.count { |h| h =~ /price|cost|wholesale|retail|amount|\$|net|dealer|msrp/i }
      finish_hits = hdr.count { |h| h =~ /unfinished|finished|paint|stain/i }
      size_hits = hdr.count { |h| h =~ /size|width|length|dim|leaf|leaves|"|x\s*\d/i }
      id_hits = hdr.count { |h| h =~ /part|item|sku|code|style|model|catalog|#/i }
      desc_hits = hdr.count { |h| h =~ /desc|name|product|title/i }
      markup_hits = hdr.count { |h| h =~ /markup|multiplier|margin|calc|factor/i }
      color_hits = hdr.count { |h| h =~ /color|colour|poly|fabric|upholstery/i }

      layout = "unknown"
      if markup_hits >= 1 && price_hits >= 1
        layout = "calculator_markup"
      elsif species_hits >= 2
        layout = "wide_species"
      elsif finish_hits >= 2 || (finish_hits >= 1 && price_hits >= 2)
        layout = "wide_finish_channel"
      elsif color_hits >= 3 || (color_hits >= 2 && price_hits >= 1)
        layout = "wide_color_matrix"
      elsif size_hits >= 2 && price_hits >= 1
        layout = "matrix_size_options"
      elsif id_hits >= 1 && (desc_hits >= 1 || price_hits >= 1) && species_hits < 2
        layout = "long_flat"
      elsif price_hits >= 1
        layout = "price_present_other"
      elsif hdr.any?
        layout = "headers_no_price_detected"
      end

      # also peek sample values for multi-price detection
      sample_vals = row_data[0, 12].flat_map { |r| r["cells"] }
      money_count = sample_vals.count { |c| c =~ /^\$?[\d,]+\.?\d*$/ && c =~ /\d/ }

      out["sheets"] << {
        "name" => name,
        "dim" => ref,
        "header_row" => header ? header["r"] : nil,
        "header" => hdr,
        "layout" => layout,
        "signals" => {
          "species" => species_hits,
          "price" => price_hits,
          "finish" => finish_hits,
          "size" => size_hits,
          "id" => id_hits,
          "desc" => desc_hits,
          "markup" => markup_hits,
          "color" => color_hits,
          "money_vals_sample" => money_count
        },
        "sample" => row_data.first(10).map { |r| { "r" => r["r"], "c" => r["cells"].first(12) } }
      }
    end
  end
  out
rescue => e
  { "file" => File.basename(path), "path" => path, "error" => "#{e.class}: #{e.message}", "sheets" => [] }
end

files = File.readlines(ARGV[0] || "/tmp/pb_files.txt").map(&:strip).reject(&:empty?)
results = files.map { |f| analyze(f) }

layouts = Hash.new(0)
header_tokens = Hash.new(0)
per_file_layout = []

results.each do |r|
  if r["error"]
    per_file_layout << { "file" => r["file"], "error" => r["error"] }
    next
  end
  # primary sheet = first with most signals
  best = r["sheets"].max_by do |s|
    sig = s["signals"] || {}
    (sig["price"] || 0) * 3 + (sig["species"] || 0) * 2 + (sig["id"] || 0) + (sig["money_vals_sample"] || 0)
  end
  primary = best ? best["layout"] : "empty"
  layouts[primary] += 1
  per_file_layout << {
    "file" => r["file"],
    "primary_layout" => primary,
    "sheets" => r["sheets"].map { |s| { "name" => s["name"], "layout" => s["layout"], "header" => s["header"] } }
  }
  r["sheets"].each do |s|
    layouts["__sheet__#{s['layout']}"] += 1
    (s["header"] || []).each do |h|
      h.to_s.downcase.split(/[\s\/\-_|,]+/).each do |tok|
        tok = tok.gsub(/[^a-z0-9#]/, "")
        next if tok.length < 2
        header_tokens[tok] += 1
      end
    end
  end
end

puts "=== FILE PRIMARY LAYOUT COUNTS ==="
layouts.select { |k, _| !k.start_with?("__sheet__") }.sort_by { |_, v| -v }.each do |k, v|
  puts "#{v}\t#{k}"
end

puts "\n=== SHEET LAYOUT COUNTS ==="
layouts.select { |k, _| k.start_with?("__sheet__") }.sort_by { |_, v| -v }.each do |k, v|
  puts "#{v}\t#{k.sub('__sheet__', '')}"
end

puts "\n=== TOP HEADER TOKENS ==="
header_tokens.sort_by { |_, v| -v }.first(50).each { |k, v| puts "#{v}\t#{k}" }

puts "\n=== PER FILE DETAIL ==="
results.each do |r|
  if r["error"]
    puts "ERR\t#{r['file']}\t#{r['error']}"
    next
  end
  r["sheets"].each do |s|
    puts [
      s["layout"],
      r["file"],
      "[#{s['name']}]",
      "hdr@#{s['header_row']}",
      (s["header"] || []).first(14).join(" | ")
    ].join("\t")
  end
end

# dump JSON for further use
File.write("/tmp/pb_layout_analysis.json", JSON.pretty_generate(results))
puts "\nWrote /tmp/pb_layout_analysis.json (#{results.size} files)"
