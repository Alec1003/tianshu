    @pytest.mark.asyncio
    async def test_error_finish(self):
        lines = [l async for l in to_ai_sdk_stream(_a(RuntimeEvent.error("bad"), RuntimeEvent.finish("error")))]
        j = "".join(lines)
        assert "error" in j
        assert "finish" in j
