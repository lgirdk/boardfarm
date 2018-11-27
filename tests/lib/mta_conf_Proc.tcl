set VERSION "1.0.4"
package require asn
proc run { parameters } {
	global VERSION
	set optionnum [llength $parameters]
	if { $optionnum == 0 } {
		puts "MTA configure file Encode/Decode rev.$VERSION"
		puts "Usage:run \[list input_file \[option\]\]"
		puts "option:"
		puts "\[General\]"
		puts "-e        Encode a MTA configuration file"
		puts "-d        Decode a MTA configuration file"
		puts "-m        Use MD5 as config file hash signature (default is SHA1)"
		puts "-hash     Add config hash (non (default), na, eu)"
		puts "-out      Specify a output filename (for encode use)"
		puts "run \[list mta.txt -e -hash eu\]"
		return
	}
	set input_file [file normalize [lindex $parameters 0]]
	if { ![file exist $input_file] } {
		puts "$input_file not available!"
		return
	}
	set optionlist [list "-e" "-out" "-d" "-hash" "-m"]
	set options [lrange $parameters 1 end]
	foreach op $options {
		if { [regexp {^-\w+$} $op] } {
			if { [lsearch $optionlist $op] == -1 } {
				puts "No such option \"$op\""
				return
			}
		}
	}
	if { [lsearch $options "-e"] != -1 && [lsearch $options "-d"] != -1 } {
		puts "Cannot Encode/Decode at the same time!"
		return
	}
	if { [lsearch $options "-out"] != -1 } {
		set filename [file normalize [lindex $options [expr [lsearch $options "-out"]+1]]]
	} else {
		if { [lsearch $options "-e"] != -1 } {
			set filename "[file rootname $input_file].bin"
		} elseif { [lsearch $options "-d"] != -1 } {
			set filename "[file rootname $input_file].txt"
		}
	}
	set hash_type "non"
	if { [lsearch $options "-hash"] != -1 } {
		set hash_type [lindex $options [expr [lsearch $options "-hash"]+1]]
		if { [lsearch [list "non" "na" "eu"] $hash_type] == -1 } {
			puts "hash type $hash_type not available!"
			return
		}
	}
	set sig_type "sha1"
	if { [lsearch $options "-e"] != -1 && $hash_type != "non" } {
		if { [lsearch $options "-m"] != -1 } {
			set sig_type "md5"
		} else {
			set sig_type "sha1"
		}
	}
	if { [lsearch $options "-e"] != -1 } {
		set hexstring "FE0101"
		set fd [open $input_file r]
		while { ![eof $fd] } {
			gets $fd line
			if { [string trim $line] == "" } { continue }
			set clist [split $line "\t"]
			if { [llength $clist] == 5 } {
				set mibname [lindex $clist 0]
				set oid [lindex $clist 1]
				set value [lindex $clist 2]
				set type [lindex $clist 3]
				set comment [lindex $clist 4]
			} else {
				puts "\[ERROR\] Incorrect source MTA config file format!"
				close $fd
				exit
			}
			if { $oid == ".1.3.6.1.4.1.7432.1.1.2.9.0" } { continue }
			if { $oid == ".1.3.6.1.4.1.4491.2.2.1.1.2.7.0" } { continue }
			set htlv [add_tlv11 $oid $value $type]
			append hexstring $htlv
		}
		close $fd
		if { $hexstring == "FE0101" } {
			puts "\[ERROR\] Could not find any MTA config setting in the file!"
			exit
		}
		set before_hash $hexstring
		append hexstring "FE01FF"
		set BStr [binary format H* $hexstring]
		if { $hash_type != "non" } {
			if { $sig_type == "sha1" } {
				package require sha1
				set hash [string toupper [::sha1::sha1 -hex $BStr]]
			} else {
				package require md5
				set hash [string toupper [::md5::md5 -hex $BStr]]
			}
			switch -- $hash_type {
				"na" {
					append before_hash [add_tlv11 ".1.3.6.1.4.1.4491.2.2.1.1.2.7.0" $hash "octetstring"]
				}
				"eu" {
					append before_hash [add_tlv11 ".1.3.6.1.4.1.7432.1.1.2.9.0" $hash "octetstring"]
				}
			}
		}
		append before_hash "FE01FF"
		set BStr [binary format H* $before_hash]
		set fd [open $filename w]
		fconfigure $fd -translation binary
		puts -nonewline $fd $BStr
		close $fd
	} elseif { [lsearch $options "-d"] != -1 } {
		dec_conf $input_file $filename
	}
}
proc enc_hexstring { value } {
	binary scan $value c* sl
	set tmp ""
	foreach s $sl {
		append tmp [format "%02X" $s]
	}
	return $tmp
}
proc enc_ui32 { value } {
	if { $value > 127 } {
		return [format "%04X" $value]
	} else {
		return [format "%02X" $value]
	}
}
proc enc_int { value } {
	if { [regexp {^\-} $value] } {
		set tmp [string range [enc_hexstring [binary format I $value]] end-7 end]
	} else {
		set tmp [format "%02X" $value]
		if { [string length $tmp]%2 != 0 } {
			set tmp "0$tmp"
		}
	}
	return $tmp
}
proc enc_ip { value } {
	set ipl [split $value "."]
	set tmp ""
	foreach ip $ipl {
		append tmp [format "%02X" $ip]
	}
	return $tmp
}
proc add_tlv11 { oid value type } {
	set tmp ""
	set eoid [::asn::asnObjectIdentifier [split [string trim $oid .] .]]
	switch -- $type {
		"int" {
			if { [regexp {^\-} $value] } {
				set evalue [enc_int $value]
				set vl [format "%02X" [expr [string length $evalue]/2]]
				set evalue [binary format H* "02$vl$evalue"]
			} else {
				set evalue [::asn::asnInteger $value]
			}
		}
		"bitstring" {
			set evalue [::asn::asnBitString "$value[string repeat 0 [expr 8-[string length $value]]]"]
		}
		"string" {
			set evalue [::asn::asnOctetString $value]
		}
		"null" {
			set evalue [::asn::asnNull]
		}
		"OID" {
			set evalue [::asn::asnObjectIdentifier [split [string trim $value .] .]]
		}
		"ipaddr" {
			set evalue [enc_ip $value]
			set vl [format "%02X" [expr [string length $evalue]/2]]
			set evalue [binary format H* "40$vl$evalue"]
		}
		"counter" {
			set evalue [enc_int $value]
			set vl [format "%02X" [expr [string length $evalue]/2]]
			set evalue [binary format H* "41$vl$evalue"]
		}
		"unsigned32" {
			set evalue [enc_ui32 $value]
			set vl [format "%02X" [expr [string length $evalue]/2]]
			set evalue [binary format H* "42$vl$evalue"]
		}
		"timeticks" {
			set evalue [enc_int $value]
			set vl [format "%02X" [expr [string length $evalue]/2]]
			set evalue [binary format H* "43$vl$evalue"]
		}
		"octetstring" {
			set evalue [::asn::asnOctetString [binary format H* $value]]
		}
	}
	binary scan [::asn::asnSequence $eoid $evalue] H* tmp
	set tmp [string toupper $tmp]
	set tl [format "%02X" [expr [string length $tmp]/2]]
	if { [string length $tl]%2 != 0 } {
		set tl "0$tl"
	}
	if { [string length $tl] != 2 } {
		return "40$tl$tmp"
	} else {
		return "0B$tl$tmp"
	}
}
proc tobyte { str } {
	set tmp [list]
	set i 0
	set max [string length $str]
	while { $i < $max } {
		lappend tmp [string range $str $i [expr $i+1]]
		incr i 2
	}
	return $tmp
}
proc dec_oid { value } {
	::asn::asnGetObjectIdentifier value oid
	return ".[join $oid "."]"
}
proc dec_conf { src {dst "" } } {
	set fd [open $src r]
	fconfigure $fd -translation binary
	set raw [read $fd [file size $src]]
	close $fd
	binary scan $raw "H*" raw
	set raw [string toupper [string range $raw 6 end-6]]
	set fd [open $dst w]
	while { $raw!= "" } {
		set tlvtmp [list ""]
		set tag [string range $raw 0 1]
		set i 2
		switch -- $tag {
			"0B" {
				set tlb 1
			}
			"40" {
				set tlb 2
			}
		}
		set tl [format "%d" 0x[string range $raw $i [expr $i+2*$tlb-1]]]
		incr i [expr 2*$tlb]
		set tmp [string range $raw $i [expr $i+2*$tl-1]]
		incr i [expr 2*$tl]
		switch -- $tlb {
			1 {
				set tmp [string range $tmp 4 end]
			}
			2 {
				set tmp [string range $tmp 8 end]
			}
		}
		set ol [format "%d" 0x[string range $tmp 2 3]]
		set ind [expr 4+2*$ol]
		set boid [binary format H* [string range $tmp 0 [expr $ind-1]]]
		set oid [dec_oid $boid]
		lappend tlvtmp $oid
		set bvstr [binary format H* [string range $tmp $ind end]]
		set vt [string range $tmp $ind [expr $ind+1]]
		incr ind 2
		set vlx [string range $tmp $ind [expr $ind+1]]
		incr ind 2
		if { $vlx == "82" } {
			set vlx [string range $tmp $ind [expr $ind+3]]
			incr ind 4
		}
		set vl [format "%d" 0x$vlx]
		set ev [string range $tmp $ind [expr $ind+$vl*2-1]]
		switch -- $vt {
			"02" {
				set type "int"
				::asn::asnGetInteger bvstr value
			}
			"03" {
				set type "bitstring"
				::asn::asnGetBitString bvstr value
			}
			"05" {
				set type "null"
				set value ""
			}
			"06" {
				set type "OID"
				set value [dec_oid $bvstr]
			}
			"40" {
				set type "ipaddr"
				set ipb [tobyte $ev]
				set ipl [list]
				foreach ip $ipb {
					lappend ipl [format "%d" 0x$ip]
				}
				set value [join $ipl "."]
			}
			"41" {
				set type "counter"
				set value [format %d 0x$ev]
			}
			"42" {
				set type "unsigned32"
				set value [format %d 0x$ev]
			}
			"43" {
				set type "timeticks"
				set value [format %d 0x$ev]
			}
			default {
				::asn::asnGetOctetString bvstr value
				regexp "\[\[:print:\]\]+" $value match
				if { [string length $match] == $vl || $vl == 0 } {
					set type "string"
				} else {
					set type "octetstring"
					binary scan $value H* value
					set value [string toupper $value]
				}
			}
		}
		lappend tlvtmp $value $type ""
		puts $fd [join $tlvtmp "\t"]
		set raw [string range $raw $i end]
	}
	close $fd
}
