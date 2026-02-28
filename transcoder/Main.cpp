// tcd - a hybrid transcoder using DVSI hardware and Codec2 software
// Copyright © 2021,2023 Thomas A. Early N7TAE
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include <unistd.h>
#include <iostream>
#include <streambuf>
#include <ctime>

#include "Controller.h"
#include "Configure.h"

// Prepends an ISO 8601 UTC timestamp to every line written to a stream.
class CTimestampBuf : public std::streambuf
{
public:
	CTimestampBuf(std::streambuf *orig) : m_orig(orig), m_newline(true) {}
protected:
	int overflow(int c) override
	{
		if (c == EOF) return EOF;
		if (m_newline)
		{
			auto now = std::time(nullptr);
			struct tm t;
			gmtime_r(&now, &t);
			char buf[32];
			strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ ", &t);
			for (const char *p = buf; *p; ++p)
				m_orig->sputc(*p);
			m_newline = false;
		}
		if (c == '\n') m_newline = true;
		return m_orig->sputc(c);
	}
	int sync() override { return m_orig->pubsync(); }
private:
	std::streambuf *m_orig;
	bool m_newline;
};

// the global objects
CConfigure  g_Conf;
CController g_Cont;

int main(int argc, char *argv[])
{
	CTimestampBuf tsbuf_out(std::cout.rdbuf());
	CTimestampBuf tsbuf_err(std::cerr.rdbuf());
	std::cout.rdbuf(&tsbuf_out);
	std::cerr.rdbuf(&tsbuf_err);
	std::cout << std::unitbuf;
	std::cerr << std::unitbuf;

	if (2 != argc)
	{
		std::cerr << "ERROR: Usage: " << argv[0] << " PATHTOINIFILE" << std::endl;
		return EXIT_FAILURE;
	}

	if (g_Conf.ReadData(argv[1]))
		return EXIT_FAILURE;

	if (g_Cont.Start())
		return EXIT_FAILURE;

	std::cout << "Hybrid Transcoder version 0.2.0 successfully started" << std::endl;

	pause();

	g_Cont.Stop();

	return EXIT_SUCCESS;
}
